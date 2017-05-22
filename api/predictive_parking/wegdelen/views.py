# Create your views here.

from datapunt import rest

from django.http import HttpResponse
from django.template import loader

from django.contrib.gis.db.models.functions import Transform

from . import models
from . import serializers


class WegdelenViewSet(rest.DatapuntViewSet):
    """
    Wegdelen

    Dit is de brondata voor:

    https://acc.parkeren.data.amsterdam.nl/

    """

    queryset = models.WegDeel.objects.order_by('id')

    serializer_class = serializers.WegDeelList
    serializer_detail_class = serializers.WegDeel

    lookup_value_regex = '[^/]+'

    filter_fields = (
        'vakken',
        'scan_count',
    )
    # filter_class = MetingenFilter


class VakkenViewSet(rest.DatapuntViewSet):
    """
    Parkeer Vakken

    Dit is de brondata voor:

    https://acc.parkeren.data.amsterdam.nl/

    """

    queryset = models.Parkeervak.objects.order_by('id')

    serializer_class = serializers.ParkeerVakList
    serializer_detail_class = serializers.ParkeerVak

    lookup_value_regex = '[^/]+'

    filter_fields = (
        'scan_count',
    )


def verdachte_vakken_view(request):
    """
    Show simple view of bad vakken
    with panorama image.
    """

    template = loader.get_template('wegdelen/simple.html')

    buurt = request.GET.get('buurt', 'A')
    aantal = int(request.GET.get('aantal', '5'))

    assert len(buurt) <= 4

    queryset = models.Parkeervak.objects.all()
    queryset = queryset.filter(buurt__startswith=buurt)
    queryset = queryset.filter(soort='FISCAAL')

    totaal_count = queryset.count()

    vakken = queryset.filter(scan_count__lte=aantal)

    null_vakken = queryset.filter(scan_count=None)
    vout = vakken | null_vakken

    latlon = []

    for vlak in vout:
        lat = vlak.geometrie.centroid.y
        lon = vlak.geometrie.centroid.x
        latlon.append((lat, lon))

    for vlak in vout:
        vlak.geometrie.transform(28992)

    context = {
        'totaal_beschikbaar': totaal_count,
        'totaal_fout': vout.count(),
        'buurt': buurt,
        'vakken': zip(latlon, vout)}

    return HttpResponse(template.render(context, request))


def verdachte_bgt_parkeervlak(request):
    """
    Show waarschijnlijk niet goed ingetekende bgt parkeervlakken
    GRATIS PARKEREN.
    """
    template = loader.get_template('wegdelen/gratis.html')

    parkeervlakken = models.WegDeel.objects.filter(bgt_functie='parkeervlak')
    qs = parkeervlakken.filter(scan_count__gte=15)
    gratis = qs.order_by('-scan_count')

    vlakken_count = parkeervlakken.count()

    latlon = []

    for vlak in gratis:
        lat = vlak.geometrie.centroid.y
        lon = vlak.geometrie.centroid.x
        latlon.append((lat, lon))

    for vlak in gratis:
        vlak.geometrie.transform(28992)

    context = {
        'totaal_vlakken': vlakken_count,
        'totaal_fout': gratis.count(),
        'vakken': zip(latlon, gratis)}

    return HttpResponse(template.render(context, request))


