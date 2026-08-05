from django.contrib import admin

from .models import Facility, FacilityAssignment, FacilityCategory, Supply

admin.site.register(FacilityCategory)
admin.site.register(Facility)
admin.site.register(FacilityAssignment)
admin.site.register(Supply)
