from django.contrib import admin

from .models import ClassGroup, Guardian, Learner, Pathway

admin.site.register(Pathway)
admin.site.register(Guardian)
admin.site.register(ClassGroup)


@admin.register(Learner)
class LearnerAdmin(admin.ModelAdmin):
    list_display = ("admission_number", "full_name", "grade", "stream", "pathway", "school")
    list_filter = ("school", "grade", "pathway")
    search_fields = ("admission_number", "upi", "first_name", "last_name")
