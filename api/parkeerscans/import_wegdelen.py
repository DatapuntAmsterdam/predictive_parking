"""
Modify scan data so we can work with it.
Importing is done with a golang script
into the scan_scan table
"""

import os
import logging

# from collections import OrderedDict
# from django.conf import settings
from django.db import connection
# rom django.db.utils import DataError

from wegdelen.models import WegDeel
from wegdelen.models import Parkeervak
# from scans.models import Scan     # Processed scans
# from scans.models import ScanRaw  # Input scans
from wegdelen.models import Buurt

from logdecorator import LogWith


logging.basicConfig(level=logging.DEBUG)

log = logging.getLogger(__name__)


@LogWith(log)
def fix_pv_geometrie_field():
    """
    Add 4326 field to parkeervakken
    """
    log.debug('Convert field geometry 4326')
    with connection.cursor() as c:
            c.execute("""
    ALTER TABLE bv.parkeervakken
    ADD COLUMN geomw geometry(MULTIPOLYGON, 4326)
    """)
            c.execute("""
    UPDATE bv.parkeervakken
    SET geomw=ST_Transform(geom, 4326)
    """)


@LogWith(log)
def make_scans_unlogged():
    """
    unlogged tables are faster!
    """
    log.debug('Alter table to UNLOGGED')
    with connection.cursor() as c:
            c.execute("""
    ALTER TABLE metingen_scan SET UNLOGGED
    """)
            c.execute("""

    ALTER TABLE metingen_scanraw SET UNLOGGED
    """)


@LogWith(log)
def make_scans_logged():
    """
    logged tables are saved on disk..
    """
    log.debug('Alter scantables to LOGGED')

    rows = collect_scans_table_list_stmt()

    with connection.cursor() as c:
        for tablename in rows:
            c.execute(f"""
    ALTER TABLE {tablename} SET LOGGED
    """)


@LogWith(log)
def fix_bgt_geometrie_field():
    """
    Add 4326 field to parkeervakken
    """
    log.debug('Convert field geometry 4326')
    with connection.cursor() as c:
            c.execute("""
    ALTER TABLE bgt.bgt_wegdeel
    ADD COLUMN geomw geometry(CurvePolygon, 4326)
    """)
            c.execute("""
    UPDATE bgt.bgt_wegdeel
    SET geomw=ST_Transform(geometrie, 4326)
    """)


@LogWith(log)
def cluster_geometrieindexen():
    log.debug('CLUSTER wegdelen takes ~1m')
    with connection.cursor() as c:
        c.execute(f"""
        CLUSTER wegdelen_parkeervak_geometrie_id on wegdelen_parkeervak;
        CLUSTER wegdelen_wegdeel_geometrie_id on wegdelen_wegdeel;
        """)


@LogWith(log)
def scan_moment_index(tablename='metingen_scan'):
    with connection.cursor() as c:
        c.execute(f"""
        CREATE INDEX ON {tablename} (scan_moment);
        """)


def store_row_data(rows):

    with open('/app/data/tables.txt', 'w') as output:
        for tablename in rows:
            log.debug(f'table: {tablename}')
            output.write(f"{tablename}\n")


def collect_scans_table_list_stmt():
    with connection.cursor() as c:
        c.execute(f"""
        SELECT table_name
        FROM information_schema.tables t
        WHERE t.table_schema LIKE 'public' AND table_name LIKE 'scans_%'
        ORDER BY table_schema,table_name;
        """)

        rows = []
        row = c.fetchone()

        while row is not None:
            rows.append(row)
            log.debug(f'Tablename: {row[0]}')
            row = c.fetchone()

        log.debug(f'Scan Tablename: {len(rows)}')
        return [r[0] for r in rows]


def collect_scans_table_list():
    rows = collect_scans_table_list_stmt()
    store_row_data(rows)


@LogWith(log)
def add_wegdeel_to_parkeervak(distance=0.000049):
    """
    Each parking spot should have a wegdeel
    """
    log.debug('Add wegdeel to each parking spot %.9f', distance)

    with connection.cursor() as c:
        c.execute(f"""
    UPDATE wegdelen_parkeervak pv
    SET bgt_wegdeel = wd.bgt_id, bgt_wegdeel_functie = wd.bgt_functie
    FROM wegdelen_wegdeel wd
    WHERE (
        wd.bgt_functie LIKE 'rijbaan lokale weg'
        OR wd.bgt_functie LIKE 'rijbaan regionale weg'
        OR wd.bgt_functie LIKE 'transitie')
    AND
    ST_DWithin(wd.geometrie, pv.geometrie, {distance})
    """)

    pv_no_wd_count = (
        Parkeervak.objects
        .filter(bgt_wegdeel=None)
        .filter(soort="FISCAAL")
        .count())

    log.info(
        "Fiscale Parkeervakken zonder WegDeel %s van %s",
        pv_no_wd_count,
        Parkeervak.objects.count())


def sql_count(table):

    c_stmt = f"SELECT COUNT(*) FROM {table};"
    count = 0

    with connection.cursor() as c:
        c.execute(c_stmt)
        row = c.fetchone()
        count += row[0]
        log.info('COUNT %s %s', table, count)

    return count


@LogWith(log)
def import_parkeervakken():
    log.info('Import en Converteer parkeervakken naar WGS84')

    Parkeervak.objects.all().delete()

    with connection.cursor() as c:
        c.execute("""
    INSERT INTO wegdelen_parkeervak(
        id,
        straatnaam,
        soort,
        type,
        aantal,
        geometrie,
        point
        )
    SELECT
        parkeer_id,
        straatnaam,
        soort,
        type,
        aantal,
        ST_Transform(ST_SetSRID(geom, 28992), 4326),
        ST_Centroid(ST_Transform(ST_SetSRID(geom, 28992), 4326))
    FROM bv.parkeervakken pv
    """)

    log.info("Alle    Vakken %s", Parkeervak.objects.all().count())
    log.info(
        "Fiscale Vakken %s",
        Parkeervak.objects.filter(soort='FISCAAL').count())


def import_bgt_wegdelen_from(bron, functie):
    """
    Importeerd data uit verschillende bronnen
    """
    log.info("Starting Wegdelen %s %s", WegDeel.objects.all().count(), bron)

    with connection.cursor() as c:
        c.execute(f"""
    INSERT INTO wegdelen_wegdeel(
        bgt_id,
        bgt_functie,
        geometrie
    )
    SELECT
        identificatie_lokaalid,
        wd."{functie}",
        ST_CurveToLine(ST_Transform(ST_SetSRID(geometrie, 28992), 4326))
    FROM bgt."{bron}" wd
    """)

    log.info("Done Wegdelen %s %s", WegDeel.objects.all().count(), bron)


@LogWith(log)
def import_wegdelen():
    log.info('Importeer en Converteer wegdelen naar WGS84 Polygonen')

    WegDeel.objects.all().delete()

    bronnen = [
        ('BGT_OWGL_verkeerseiland', 'bgt_functie'),
        ('BGT_OWGL_berm', 'bgt_fysiekvoorkomen'),
        ('BGT_OTRN_open_verharding', 'bgt_fysiekvoorkomen'),
        ('BGT_OTRN_transitie', 'bgt_fysiekvoorkomen'),
        ('BGT_WGL_fietspad', 'bgt_functie'),
        ('BGT_WGL_voetgangersgebied', 'bgt_functie'),
        ('BGT_WGL_voetpad', 'bgt_functie'),
        ('BGT_WGL_parkeervlak', 'bgt_functie'),
        ('BGT_WGL_rijbaan_lokale_weg', 'bgt_functie'),
        ('BGT_WGL_rijbaan_regionale_weg', 'bgt_functie'),
    ]
    for bron, functie in bronnen:
        import_bgt_wegdelen_from(bron, functie)


@LogWith(log)
def import_buurten():
    """
    Build buurt dataset where we can add parkeervak information
    """
    Buurt.objects.all().delete()

    log.info('Create buurten dataset < 1 min')
    with connection.cursor() as c:
        c.execute("""
    INSERT INTO wegdelen_buurt(
        id,
        code,
        naam,
        geometrie
    )
    SELECT
        id,
        vollcode,
        naam,
        ST_Transform(geometrie, 4326)
    FROM bag_buurt
    """)


@LogWith(log)
def add_buurt_to_parkeervak():
    """
    Given parkeervakken find buurt of each pv
    """
    log.info('Add buurtcode to each parkeervak < 1 min')

    with connection.cursor() as c:
        c.execute("""
    UPDATE  wegdelen_parkeervak pv
    SET buurt = b.code
    FROM wegdelen_buurt b
    WHERE ST_DWithin(b.geometrie, pv.point, 0)
    """)

    log.info(
       "Parkeervak zonder buurt %s",
       Parkeervak.objects.filter(buurt=None).count())


@LogWith(log)
def add_buurt_to_wegdelen():
    """
    Given wegdeel find buurt of each wegdeel which has vakken.
    """
    log.info('Add buurtcode to each wegdeel < 1 min')

    with connection.cursor() as c:
        c.execute("""
    UPDATE  wegdelen_wegdeel wd
    SET buurt = b.code
    FROM wegdelen_buurt b
    WHERE ST_DWithin(b.geometrie, st_centroid(wd.geometrie), 0)
    AND wd.vakken is not null
    """)

    log.info(
        "Wegdelen in Amsterdam zonder buurt %s",
        WegDeel.objects.filter(buurt=None).filter(vakken__isnull=False).count()
    )


@LogWith(log)
def add_parkeervak_count_to_wegdeel():
    """
    Each wegdeel needs to have a count of parkeervakken.
    """
    log.info('Add parkeervak count to each wegdeel ~ 1 min')

    def status(state):

        log.info(
            "%6s Wegdelen met parkeervak count %s",
            state,
            WegDeel.objects.filter(vakken__gt=0).count())

        log.info(
            "%6s Wegdelen met fiscale pv count %s",
            state,
            WegDeel.objects.filter(fiscale_vakken__gt=0).count())

    status('before')

    with connection.cursor() as c:
        c.execute("""

    UPDATE wegdelen_wegdeel wd SET vakken=sq.vakken
    FROM (
        SELECT bgt_wegdeel, count(id) as vakken
        FROM wegdelen_parkeervak
            GROUP BY bgt_wegdeel
        )
        AS sq
        WHERE wd.bgt_id = bgt_wegdeel
    """)

    with connection.cursor() as c:
        c.execute("""
    UPDATE wegdelen_wegdeel wd SET fiscale_vakken=sq.vakken
    FROM (
        SELECT bgt_wegdeel, count(id) as vakken
        FROM wegdelen_parkeervak
        WHERE soort = 'FISCAAL'
            GROUP BY bgt_wegdeel
        )
        AS sq
        WHERE wd.bgt_id = bgt_wegdeel
    """)

    status('after')


@LogWith(log)
def add_parkeervak_count_to_buurt():
    """
    Each buurt needs to have count of parkeervakken
    """
    log.debug('Add parkeervak count to each buurt < (1 min)')

    def status(state):
        log.debug(
            "%6s: Buurt zonder pv count %s",
            state,
            Buurt.objects.filter(vakken=None).count())

        log.debug(
            "%6s: Buurt zonder fiscale vakken count %s",
            state,
            Buurt.objects.filter(fiscale_vakken=None).count())

    status('before')

    with connection.cursor() as c:
        c.execute("""
    UPDATE wegdelen_buurt b SET vakken=sq.vakken
    FROM (
        SELECT buurt, count(id) as vakken
        FROM wegdelen_parkeervak
            GROUP BY buurt
        )
        AS sq
        WHERE code = buurt
    """)

    with connection.cursor() as c:
        c.execute("""
    UPDATE wegdelen_buurt b SET fiscale_vakken=sq.vakken
    FROM (
        SELECT buurt, count(id) as vakken
        FROM wegdelen_parkeervak
        WHERE soort = 'FISCAAL'
            GROUP BY buurt
        )
        AS sq
        WHERE code = buurt
    """)

    status('after')


@LogWith(log)
def create_scan_sample_table():
    """
    Create scan sample viewset ~2.000.000 items
    """

    rows = collect_scans_table_list_stmt()

    rows.reverse()

    sample_table = "scans_sample"

    def status(state):
        count = sql_count(sample_table)
        log.debug("%6s: Sample scans count %s", state, count)
        return count

    drop_if = f"""
        DROP TABLE IF EXISTS {sample_table};
    """

    create_sample_stm = f"""

    CREATE UNLOGGED TABLE {sample_table} (
        LIKE metingen_scan INCLUDING DEFAULTS INCLUDING CONSTRAINTS);

    """

    with connection.cursor() as c:
        c.execute(drop_if)

    with connection.cursor() as c:
        c.execute(create_sample_stm)

    for table_name in rows[:4]:
        log.debug('SAMPLE %s', table_name)

        insert_stm = f"""
            INSERT INTO {sample_table}
            SELECT * FROM {table_name};
        """

        with connection.cursor() as c:
            c.execute(insert_stm)

    count = status('after')

    if os.getenv('TESTING') == 'yes':
        return

    assert count > 0


@LogWith(log)
def add_scan_count_wegdelen_vakken():
    """
    Find the last 3 scan tables and add counts to
    """
    rows = collect_scans_table_list_stmt()
    total_scans = 0
    # newest first
    rows.reverse()

    for table in rows:

        idx_wegdeel = f"CREATE INDEX ON {table} (bgt_wegdeel);"
        idx_pvid = f"CREATE INDEX ON {table} (parkeervak_id);"

        with connection.cursor() as c:
            log.debug('INDEX on Wegdeel %s', table)
            c.execute(idx_wegdeel)
        with connection.cursor() as c:
            log.debug('INDEX on Parkeervak %s', table)
            c.execute(idx_pvid)

        count = sql_count(table)
        total_scans += count

        log.debug('COUNT %s %s', table, total_scans)

        add_scan_count_to_wegdelen(table)

        add_scan_count_to_vakken(table)

        if total_scans > 9800000:
            log.debug(f'We have enough sample data sample size: {total_scans}')
            break


@LogWith(log)
def add_scan_count_to_wegdelen(source_table):

    log.debug('Add scan count to each wegdeel using %s', source_table)

    def status(state):
        source_scan_count = sql_count(source_table)
        log.debug('scans: %s', source_scan_count)

        all_wegdeel = WegDeel.objects.count()
        null_wegdeel = WegDeel.objects.filter(scan_count=None).count()

        log.debug(
            "%6s: Wegdelen T %s NULl: %s >0: %s",
            state,
            all_wegdeel,
            null_wegdeel,
            WegDeel.objects.filter(scan_count__gt=0).count())

        assert null_wegdeel != all_wegdeel

    with connection.cursor() as c:
        c.execute(f"""
    UPDATE wegdelen_wegdeel b SET scan_count = COALESCE(scan_count, 0) + sq.scans
    FROM (
        SELECT bgt_wegdeel, count(id) as scans
        FROM {source_table}
            GROUP BY bgt_wegdeel
        )
        AS sq
        WHERE b.bgt_id = sq.bgt_wegdeel
    """)  # noqa

    status('validate')


@LogWith(log)
def add_scan_count_to_vakken(source_table):

    log.debug('Add scan count to each parkeervak using %s', source_table)

    def status(state):
        fiscaal = Parkeervak.objects.filter(soort='FISCAAL')

        all_fiscaal = fiscaal.count()
        null_vakken = fiscaal.filter(scan_count=None).count()

        log.debug(
            "%6s: Fiscale Vakken Totaal %s not seen: %s seen: %s",
            state,
            all_fiscaal,
            null_vakken,
            fiscaal.filter(scan_count__gt=0).count())

        if state == 'after':
            assert all_fiscaal != null_vakken

    status('before')

    with connection.cursor() as c:
        c.execute(f"""
    UPDATE wegdelen_parkeervak v SET scan_count = COALESCE(scan_count, 0) + sq.scans
    FROM (
        SELECT parkeervak_id, count(id) as scans
        FROM {source_table}
            GROUP BY parkeervak_id
        )
        AS sq
        WHERE v.id = sq.parkeervak_id
    """)  # noqa

    status('after')
