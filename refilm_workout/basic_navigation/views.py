# import datetime
import json
import os

# from django.conf import settings
from django.http import HttpResponse
from django.http import HttpResponseRedirect
# from django.http import HttpResponsePermanentRedirect
from django.shortcuts import render_to_response

from refilm_workout.film.models import Film
from refilm_workout.constants import Equipment


def render_to_json(data, status=200):
    return HttpResponse(json.dumps(data), content_type="application/json", status=status)


def home(request, combo_id=None):
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

    if combo_id == "bodyweight":
        try:
            exercise = Film.get_next_bodyweight_exercise()
        except ValueError:
            return HttpResponse("<h1>YOU'RE ALL DONE!  THANKS!</h1>")
    else:
        try:
            exercise = Film.get_next_exercise(combo_id)
        except ValueError:
            return HttpResponse("<h1>YOU'RE ALL DONE!  THANKS!</h1>")
    finished_count = Film.get_finished_count()
    total_count = Film.get_total_count()
    render_data = {
        "dev": True if os.environ.get("I_AM_IN_DEV_ENV") else False,
        "video_id": exercise.video_id,
        "exercise_name": exercise.name,
        "finished_count": finished_count,
        "total_count": total_count,
        "possible_equipments": _get_equipments(),
        "exercise_id": exercise.id
    }
    return render_to_response("basic_navigation/base.html", render_data)


def _get_equipments():
    tuples = Film.get_all_equipment_tuples()
    combo_to_name = {}
    for tuple_obj in tuples:
        combo_id = "_".join([str(i) for i in tuple_obj])
        display_name = ", ".join([Equipment.get_name_for_id(id) for id in tuple_obj])
        combo_to_name[combo_id] = display_name
    return combo_to_name


def remaining(request):
    exercises = Film.get_all_available()
    render_data = {
        "exercises": exercises
    }
    return render_to_response("basic_navigation/all.html", render_data)


def exercise(request, exercise_id):
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
        return HttpResponseRedirect("/")

    exercise_id = int(exercise_id)
    exercise = Film.get_by_exercise_id(exercise_id)
    render_data = {
        "video_id": exercise.video_id,
        "exercise_name": exercise.name,
        "exercise_id": exercise.id
    }
    return render_to_response("basic_navigation/exercise.html", render_data)
