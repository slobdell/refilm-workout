# import datetime
import json
import os

# from django.conf import settings
from django.http import HttpResponse
# from django.http import HttpResponseRedirect
# from django.http import HttpResponsePermanentRedirect
from django.shortcuts import render_to_response

from refilm_workout.film.models import Film


def render_to_json(data, status=200):
    return HttpResponse(json.dumps(data), content_type="application/json", status=status)


def home(request):
    if request.method == "POST":
        action = request.POST['action']
        action_map = {
            'discard': Film.mark_will_not_film,
            'later': Film.mark_in_progress,
            'filmed': Film.mark_filmed,
        }
        fn = action_map[action]
        exercise_id = int(request.POST['exercise_id'])
        fn(exercise_id)

    try:
        exercise = Film.get_next_exercise()
    except ValueError:
        return HttpResponse("<h1>YOU'RE ALL DONE!  THANKS!</h1>")
    render_data = {
        "dev": True if os.environ.get("I_AM_IN_DEV_ENV") else False,
        "video_id": exercise.video_id,
        "exercise_name": exercise.name,
        "exercise_id": exercise.id
    }
    return render_to_response("basic_navigation/base.html", render_data)
