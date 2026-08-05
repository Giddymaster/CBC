from django.contrib import admin

from .models import Lesson, Period, Room

admin.site.register(Room)
admin.site.register(Period)
admin.site.register(Lesson)
