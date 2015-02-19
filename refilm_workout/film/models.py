import datetime
from collections import defaultdict

# from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from refilm_workout.utils import read_file_as_json


EXPIRE_MINUTES = 30  # 2 * 31 * 24 * 60 * 60


class FilmState(object):
    NEEDS_REFILM = 1
    REFILMED = 2
    IN_PROGRESS = 3
    WILL_NOT_FILM = 4


class _Film(models.Model):
    film_state_id = models.IntegerField(default=FilmState.NEEDS_REFILM)
    datetime_status_changed = models.DateTimeField(null=True)
    datetime_complete = models.DateTimeField(null=True)
    exercise_id = models.IntegerField()


class Film(object):

    class _Exercise(object):

        def __init__(self, dict_obj):
            self.json_fields = []
            for key, value in dict_obj.items():
                self.json_fields.append(key)
                setattr(self, key, value)

        def to_json(self):
            json_blob = {}
            for field in self.json_fields:
                json_blob[field] = getattr(self, field)
            return json_blob

        def __hash__(self):
            return self.id

    _exercises = [_Exercise(dict_obj) for dict_obj in read_file_as_json("refilm_workout/exercises.json")]

    _exercises_by_required_equipment = defaultdict(list)
    for e in _exercises:
        required_equipment_key = tuple(sorted(e.equipment_ids))
        _exercises_by_required_equipment[required_equipment_key].append(e)

    @classmethod
    def mark_will_not_film(cls, exercise_id):
        _film = _Film.objects.get(exercise_id=exercise_id)
        _film.film_state_id = FilmState.WILL_NOT_FILM
        _film.datetime_status_changed = datetime.datetime.utcnow()
        _film.save()

    @classmethod
    def mark_in_progress(cls, exercise_id):
        _film = _Film.objects.get(exercise_id=exercise_id)
        _film.film_state_id = FilmState.IN_PROGRESS
        _film.datetime_status_changed = datetime.datetime.utcnow()
        _film.save()

    @classmethod
    def mark_filmed(cls, exercise_id):
        _film = _Film.objects.get(exercise_id=exercise_id)
        _film.film_state_id = FilmState.REFILMED
        _film.datetime_status_changed = datetime.datetime.utcnow()
        _film.datetime_complete = datetime.datetime.utcnow()
        _film.save()

    @classmethod
    def populate_initial_data(cls):
        existing_exercise_ids = set(_Film.objects.all().values_list("exercise_id", flat=True))
        for _exercise in cls._exercises:
            if _exercise.id not in existing_exercise_ids:
                _Film.objects.create(
                    film_state_id=FilmState.NEEDS_REFILM,
                    exercise_id=_exercise.id
                )

    @classmethod
    def _readd_stuck_exercises_to_pool(cls):
        (_Film.objects.filter(
            film_state_id=FilmState.IN_PROGRESS,
            datetime_status_changed__lt=datetime.datetime.utcnow() - datetime.timedelta(minutes=EXPIRE_MINUTES)).
            update(film_state_id=FilmState.NEEDS_REFILM))

    @classmethod
    def get_next_exercise(cls, combo_id_str):
        id_tuple = None
        if combo_id_str is not None:
            id_tuple = tuple([int(i) for i in combo_id_str.split("_")])
        cls._readd_stuck_exercises_to_pool()
        exercise = cls._get_first_available_exercise(id_tuple)
        _film = _Film.objects.get(exercise_id=exercise.id)
        _film.film_state_id = FilmState.IN_PROGRESS
        _film.datetime_status_changed = datetime.datetime.utcnow()
        _film.save()
        return exercise

    @classmethod
    def get_next_bodyweight_exercise(cls):
        id_tuple = tuple()
        cls._readd_stuck_exercises_to_pool()
        exercise = cls._get_first_available_exercise(id_tuple)
        _film = _Film.objects.get(exercise_id=exercise.id)
        _film.film_state_id = FilmState.IN_PROGRESS
        _film.datetime_status_changed = datetime.datetime.utcnow()
        _film.save()
        return exercise

    @classmethod
    def _get_first_available_exercise(cls, equipment_id_tuple):
        exercise_ids_need_refilming = set(_Film.objects.filter(film_state_id=FilmState.NEEDS_REFILM).values_list("exercise_id", flat=True))
        if equipment_id_tuple is not None:
            exercise_list = cls._exercises_by_required_equipment[equipment_id_tuple]
            for exercise in exercise_list:
                if exercise.id in exercise_ids_need_refilming:
                    return exercise
        else:
            for equipment_tuple, exercise_list in cls._exercises_by_required_equipment.iteritems():
                for exercise in exercise_list:
                    if exercise.id in exercise_ids_need_refilming:
                        return exercise
        raise ValueError("HEY ALRIGHT YOU ARE ALL DONE!")

    @classmethod
    def get_all_equipment_tuples(cls):
        return cls._exercises_by_required_equipment.keys()

    @classmethod
    def get_total_count(cls):
        return _Film.objects.all().count()

    @classmethod
    def get_finished_count(cls):
        return _Film.objects.all().exclude(film_state_id=FilmState.NEEDS_REFILM).count()
