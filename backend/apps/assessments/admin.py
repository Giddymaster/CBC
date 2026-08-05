from django.contrib import admin

from .models import Assessment, LearningArea, Score

admin.site.register(LearningArea)
admin.site.register(Assessment)


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ("learner", "assessment", "marks", "competency_level")
    list_filter = ("competency_level", "assessment__kind")
