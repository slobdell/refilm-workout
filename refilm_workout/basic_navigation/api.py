import json

from django.http import Http404
from django.http import HttpResponse

from workout_generator.access_token.models import AccessToken
from workout_generator.basic_navigation.constants import ResponseCodes
from workout_generator.constants import Equipment
from workout_generator.constants import Goal
from workout_generator.coupon.models import Coupon
from workout_generator.datetime_tools import get_timezone_from_utc_offset_minutes
from workout_generator.mailgun.tasks import send_verify_email
from workout_generator.stripe.constants import SubscriptionState
from workout_generator.stripe.utils import cancel_subscription
from workout_generator.stripe.utils import change_credit_card
from workout_generator.stripe.utils import create_subscription
from workout_generator.stripe.utils import validate_user_payment
from workout_generator.user.constants import StatusState
from workout_generator.user.models import User
from workout_generator.user.exceptions import NoGoalSetException
from workout_generator.utils import email_admin_on_exception
from workout_generator.workout.exceptions import NeedsNewWorkoutsException
from workout_generator.workout.models import WorkoutCollection
from workout_generator.workout.generator import generate_new_workouts


def render_to_json(response_obj, context={}, content_type="application/json", status=200):
    json_str = json.dumps(response_obj, indent=4)
    return HttpResponse(json_str, content_type=content_type, status=status)


def requires_active_state(fn):
    def inner(request, *args, **kwargs):
        user = kwargs["user"]
        # TODO just make another method on user for all this logic
        if user.has_free_membership():
            return fn(request, *args, **kwargs)
        is_valid = user.status_state == StatusState.ACTIVE
        if not is_valid:
            return _error_for_invalid_state()
        return fn(request, *args, **kwargs)
    return inner


def requires_payment(fn):
    def inner(request, *args, **kwargs):
        user = kwargs["user"]
        if user.has_free_membership():
            return fn(request, *args, **kwargs)

        subscription_state = validate_user_payment(user)
        if subscription_state != SubscriptionState.VALID:
            return _error_for_subscription_state(subscription_state)
        return fn(request, *args, **kwargs)
    return inner


def requires_auth(fn):
    def inner(request, *args, **kwargs):
        if 'username' not in request.GET:
            return render_to_json({
                "message": "GET requires a 'username'"
            }, status=400)
        username = request.GET['username']
        user = User.get_by_username(username)

        if 'access_token' not in request.GET:
            return render_to_json({
                "message": "GET requires an 'access_token'"
            }, status=400)
        access_token = AccessToken.get_from_token_data(request.GET['access_token'])
        if not access_token.has_access_to_user(user):
            return render_to_json({
                "message": "Invalid Access Token"
            }, status=403)
        kwargs['user'] = user

        return fn(request, *args, **kwargs)
    return inner


def requires_post(fn):
    def inner(request, *args, **kwargs):
        if request.method != "POST":
            return Http404

        post_data = request.POST or json.loads(request.body)
        if 'username' not in post_data:
            return render_to_json({
                "message": "POST requests require a Parse 'username'",
            }, status=400)

        username = post_data['username']
        newly_created, user = User.get_or_create_by_username(username)
        if newly_created:
            access_token = AccessToken.create_for_user(user)
        else:
            if 'access_token' not in post_data:
                return render_to_json({
                    "message": "POST request requires an access token",
                }, status=400)

            access_token = AccessToken.get_from_token_data(post_data['access_token'])
            if not access_token.has_access_to_user(user):
                return render_to_json({
                    "message": "Invalid Access Token"
                }, status=403)
        kwargs["user"] = user
        kwargs["access_token"] = access_token.token_data
        return fn(request, *args, **kwargs)
    return inner


@requires_post
def signup(request, user=None, access_token=None):
    post_data = request.POST or json.loads(request.body)
    if 'facebook' not in post_data:
        email = post_data['email']
        placeholder(email)
        send_verify_email(email, user.confirmation_code)
    else:
        user.make_confirmed()
    return render_to_json({"access_token": access_token}, status=200)


def placeholder(*args, **kwargs):
    pass


def goals(request):
    return render_to_json(Goal.as_json())


def equipment(request):
    return render_to_json(Equipment.as_json())


def user(request):
    if request.method == "POST":
        return _update_user(request)
    else:
        return _get_user(request)


@requires_post
def _update_user(request, user=None, access_token=None):
    field_to_function = {
        'goal_id': _update_goal,
        'age': _update_age,
        'gender': _update_gender,
        'equipment_ids': _update_equipment_ids,
        'enabled_days': _update_available_days,
        'minutes_per_day': _update_minutes_per_day,
        'fitness_level': _update_fitness_level,
        'experience': _update_experience
    }

    post_data = request.POST or json.loads(request.body)
    for field, function in field_to_function.items():

        if function is None:
            continue

        if field in post_data:
            function(user, post_data[field])

    return render_to_json({"access_token": access_token}, status=200)


@requires_auth
def _get_user(request, user=None):
    if not user:
        return render_to_json({}, status=400)
    return render_to_json(user.to_json())


def _update_goal(user, goal_id):
    user.update_goal_id(goal_id)


def _update_equipment_ids(user, equipment_id_list):
    user.update_equipment_ids(equipment_id_list)


def _update_available_days(user, js_isoweekday_list):
    user.update_available_days(js_isoweekday_list)


def _update_minutes_per_day(user, minutes_per_day):
    minutes_per_day = int(minutes_per_day)
    user.update_minutes_per_day(minutes_per_day)


def _update_fitness_level(user, fitness_level_id):
    fitness_level_id = int(fitness_level_id)
    user.update_fitness_level(fitness_level_id)


def _update_experience(user, experience_id):
    experience_id = int(experience_id)
    user.update_experience(experience_id)


def _update_gender(user, canonical_gender_name):
    user.update_gender(canonical_gender_name)


def _update_age(user, age):
    age = int(age)
    user.update_age(age)


@requires_post
def cancel_payment(request, user=None, access_token=None):
    cancel_subscription(user)
    return render_to_json({}, status=204)


@requires_post
def payment(request, user=None, access_token=None):
    post_data = request.POST or json.loads(request.body)
    coupon_code = post_data.get("coupon_code")

    # TODO move to its own function or something
    if coupon_code:
        coupon = Coupon.get_by_code(coupon_code)
        if coupon.valid and coupon.stripe_plan_id is None:
            user.make_free_membership()
            return render_to_json({"access_token": access_token}, status=200)

    stripe_token = post_data['tokenId']
    stripe_email = post_data['tokenEmail']
    if user.stripe_customer_id is None:
        success, customer_id_or_message = create_subscription(stripe_token, stripe_email)
        if not success:
            return render_to_json({
                "error": customer_id_or_message
            }, status=400)

        user.update_stripe_customer_id(customer_id_or_message)
    else:
        change_credit_card(user)

    return render_to_json({"access_token": access_token}, status=200)


def _error_for_invalid_state():
    return render_to_json({
        "redirect": "!requiresconfirmation"
    }, status=ResponseCodes.REDIRECT_REQUIRED)


def _error_for_subscription_state(subscription_state):
    if subscription_state == SubscriptionState.DELINQUENT:
        return render_to_json({
            "redirect": "!payment/delinquent"
        }, status=ResponseCodes.REDIRECT_REQUIRED)
    elif subscription_state == SubscriptionState.INVALID:
        return render_to_json({
            "redirect": "!payment"
        }, status=ResponseCodes.REDIRECT_REQUIRED)


@email_admin_on_exception
@requires_auth
@requires_active_state
@requires_payment
def workout(request, user=None):
    '''
    return a week's worth of data for the user
    '''
    if not user:
        return render_to_json({}, status=400)
    utc_offset = int(request.GET.get('utc_offset', 0))
    timezone = get_timezone_from_utc_offset_minutes(utc_offset)
    try:
        workout_collection = WorkoutCollection.for_user(user, timezone)
    except NeedsNewWorkoutsException:
        try:
            workout_collection = generate_new_workouts(user)
        except NoGoalSetException:
            return render_to_json({
                "redirect": "!goal/return"
            }, status=ResponseCodes.REDIRECT_REQUIRED)
    return render_to_json(workout_collection.to_json())


@requires_post
def re_send_confirmation(request, user=None, access_token=None):
    email = user.username
    send_verify_email(email, user.confirmation_code)
    return render_to_json({
        "email": email
    }, status=200)


def coupon(request, coupon_code):
    return render_to_json(
        Coupon.get_by_code(coupon_code).to_json(),
        status=200)
