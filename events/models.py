# coding: utf-8
from __future__ import unicode_literals
import datetime

from django.core.urlresolvers import reverse
from django.db import models
from django.contrib.sites.models import Site, get_current_site
from django.utils.datastructures import SortedDict
from django.utils.timezone import now


# In which grade does a high school student graduate?
GRADUATION_GRADE = 4


class School(models.Model):
    abbreviation = models.CharField(max_length=100,
                                    blank=True,
                                    verbose_name="skratka",
                                    help_text="Sktatka názvu školy.")
    verbose_name = models.CharField(max_length=100,
                                    verbose_name="celý názov")
    addr_name = models.CharField(max_length=100, blank=True)
    street = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)

    class Meta:
        verbose_name = "škola"
        verbose_name_plural = "školy"
        ordering = ("verbose_name",)

    def __unicode__(self):
        return self.verbose_name


class AdditionalUserDetails(models.Model):
    user = models.OneToOneField('auth.User',
                                related_name='additional_events_details')
    school = models.ForeignKey(School, default=1, verbose_name="škola",
                               help_text='Pokiaľ vaša škola nie je '
                               'v&nbsp;zozname, vyberte "Gymnázium iné" '
                               'a&nbsp;pošlite nám e-mail.')
    is_teacher = models.BooleanField(verbose_name="som učiteľ",
                                     help_text='Učitelia vedia hromadne '
                                     'prihlasovať školy na akcie.')
    graduation = models.IntegerField(blank=True, null=True,
                                     verbose_name="rok maturity",
                                     help_text="Povinné pre žiakov.")
    want_news = models.BooleanField(verbose_name="pozvánky e-mailom",
                                    help_text="Mám záujem dostávať "
                                    "e-mailom pozvánky na ďalšie akcie.")

    class Meta:
        verbose_name = "dodatočné údaje o užívateľoch"
        verbose_name_plural = "dodatočné údaje o užívateľoch"

    def __unicode__(self):
        return "%s" % (self.user,)

    def get_grade(self, date=None):
        """
        Returns the school grade based on graduation_year and the provided
        date. If no date is provided, today is used.
        """
        if date is None:
            date = datetime.date.today()
        # Normalize the given date's year to the one in which the closest
        # following graduation happens.
        # For simplicity, we assume graduation happens every year on the
        # first day of July.
        if date.month >= 7:
            date = date.replace(year=date.year + 1)
        years_to_graduation = self.graduation - date.year
        return GRADUATION_GRADE - years_to_graduation


def choose_invitation_filename(instance, original):
    return "invitations/%s.pdf" % (instance.date.isoformat(),)


class Event(models.Model):
    name = models.CharField(max_length=100,
                            help_text="Názov akcie, napr. Klub Trojstenu "
                            "po Náboji FKS")
    date = models.DateField(unique=True)
    deadline = models.DateTimeField(help_text="Deadline na prihlasovanie")
    invitation = models.FileField(upload_to=choose_invitation_filename,
                                  blank=True,
                                  help_text="PDF s pozvánkou, keď bude "
                                  "hotová.")
    sites = models.ManyToManyField(Site)

    class Meta:
        verbose_name = "akcia"
        verbose_name_plural = "akcie"
        ordering = ("-date",)

    def __unicode__(self):
        return "%s %s" % (self.name, self.date.year)

    def get_absolute_url(self):
        # We need to check if the event is the latest for this page and we
        # don't have access to the request to just call get_latest_event.
        if Event.objects.filter(sites__id__in=self.sites.all(),
                               date__gt=self.date).count() > 0:
            # There are newer relevant events, generate a general URL.
            return reverse("event_detail", kwargs={
                               'year': self.date.year,
                               'month': self.date.month,
                               'day': self.date.day,
                           })
        # Else just return the link to the latest event.
        return reverse("event_latest")

    def get_attendance_url(self):
        return "/events/%04d/%02d/%02d/attendance/" % (
            self.date.year, self.date.month, self.date.day,
        )
        # For some reason the following doesn't work ON ONE OF THE SITES.
        """
        return reverse("event_attendance", kwargs={
                           'year': self.date.year,
                           'month': self.date.month,
                           'day': self.date.day,
                       })
        """

    def get_grouped_lectures(self):
        """
        Returns the lectures for this event in a SortedDict mapping times
        to lists of lectures sorted by their rooms.
        """
        try:
            return self._grouped_lectures_cache
        except AttributeError:
            result = SortedDict()
            for lecture in self.lectures.order_by("time", "room"):
                result.setdefault(lecture.time, []).append(lecture)
            self._grouped_lectures_cache = result
            return result

    def signup_period_open(self):
        return now() < self.deadline


class Lecture(models.Model):
    event = models.ForeignKey(Event, verbose_name="akcia",
                              related_name="lectures")
    lecturer = models.CharField(max_length=100, verbose_name="prednášajúci")
    title = models.CharField(max_length=147, verbose_name="názov prednášky")
    abstract = models.TextField(blank=True, verbose_name="abstrakt")
    room = models.CharField(max_length=20, verbose_name="miestnosť")
    time = models.TimeField(verbose_name="čas")
    video_url = models.URLField(blank=True, verbose_name="URL videa")

    class Meta:
        verbose_name = "prednáška"
        verbose_name_plural = "prednášky"
        ordering = ("event", "time")

    def __unicode__(self):
        return "%s: %s" % (self.lecturer, self.title)


def get_latest_event(request):
    """
    Returns the latest event relevant for the current site.
    """
    site = get_current_site(request)
    return Event.objects.filter(sites__id__exact=site.pk).order_by('-date')[0]


class IndividualSignup(models.Model):
    event = models.ForeignKey(Event, verbose_name="akcia",
                              related_name="individual_signups")
    user = models.ForeignKey('auth.User')
    lunch = models.BooleanField(verbose_name="obed",
                                help_text="Mám záujem o obed po akcii")

    class Meta:
        verbose_name = "prihláška jednotlivca"
        verbose_name_plural = "prihlášky jednotlivcov"

    def __unicode__(self):
        return "%s, %s" % (self.user, self.event)


class IndividualOvernightSignup(IndividualSignup):
    sleepover = models.BooleanField(verbose_name="chcem prespať",
                                    help_text="Prespávanie bude v lodenici "
                                    "alebo v telocvični za poplatok, ktorý "
                                    "určí na mieste doc. Potočný.")
    sleeping_bag = models.BooleanField(verbose_name="spacák",
                                       help_text="Mám záujem požičať si "
                                       "spacák. Spacákov je obmedzené "
                                       "množstvo, takže pokiaľ môžete, "
                                       "radšej si doneste vlastné.")
    sleeping_pad = models.BooleanField(verbose_name="karimatka",
                                       help_text="Mám záujem požičať si "
                                       "karimatku. Karimatiek je obmedzené "
                                       "množstvo, takže pokiaľ môžete, "
                                       "radšej si doneste vlastné.")
    game_participation = models.BooleanField(verbose_name="zúčastním sa hry")


class SchoolSignup(models.Model):
    event = models.ForeignKey(Event, verbose_name="akcia",
                              related_name="school_signups")
    user = models.ForeignKey('auth.User')
    students1 = models.PositiveSmallIntegerField(default=0,
                                                 verbose_name="počet prvákov")
    students2 = models.PositiveSmallIntegerField(default=0,
                                                 verbose_name="počet druhákov")
    students3 = models.PositiveSmallIntegerField(default=0,
                                                 verbose_name="počet tretiakov")
    students4 = models.PositiveSmallIntegerField(default=0,
                                                 verbose_name="počet štvrtákov")
    lunches = models.PositiveSmallIntegerField(default=0,
                                               verbose_name="počet obedov")

    def get_total_students(self):
        return self.students1 + self.students2 + self.students3 + self.students4


def get_signup_model(request):
    """
    Returns the signup model relevant to current site and the logged in
    user's settings.
    """
    try:
        return request._akademia_events_signup_model
    except AttributeError:
        if get_current_site(request).domain == 'akademia.trojsten.sk':
            if request.user.additional_events_details.is_teacher:
                model = SchoolSignup
            else:
                model = IndividualSignup
        else:
            model = IndividualOvernightSignup
        request._akademia_events_signup_model = model
        return model
