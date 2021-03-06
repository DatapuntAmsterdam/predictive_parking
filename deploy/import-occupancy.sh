#!/bin/bash

set -e
set -u

DIR="$(dirname $0)"

echo $0

#

dc() {
	docker-compose -p occ -f ${DIR}/docker-compose.yml $*;
}

# so we can delete named volumes
dc stop
dc rm -f -v

dc build
dc pull

dc up -d database

dc run --rm importer ./docker-wait.sh


echo "create pp database"
dc run --rm importer ./docker-migrate.sh

echo "Load latest parkeervakken.."
dc exec -T database update-table.sh parkeervakken parkeervakken bv parkeerscans
echo "Load latest wegdelen.."

# foutparkeerders / scans niet in vakken
dc exec -T database update-table.sh basiskaart BGT_OWGL_verkeerseiland bgt parkeerscans
dc exec -T database update-table.sh basiskaart BGT_OWGL_berm bgt parkeerscans
dc exec -T database update-table.sh basiskaart BGT_OTRN_open_verharding bgt parkeerscans
dc exec -T database update-table.sh basiskaart BGT_OTRN_transitie bgt parkeerscans
dc exec -T database update-table.sh basiskaart BGT_WGL_fietspad bgt parkeerscans
dc exec -T database update-table.sh basiskaart BGT_WGL_voetgangersgebied bgt parkeerscans
dc exec -T database update-table.sh basiskaart BGT_WGL_voetpad bgt parkeerscans



# interessante wegdelen: wegen en vakken
dc exec -T database update-table.sh basiskaart BGT_WGL_parkeervlak bgt parkeerscans
dc exec -T database update-table.sh basiskaart BGT_WGL_rijbaan_lokale_weg bgt parkeerscans
dc exec -T database update-table.sh basiskaart BGT_WGL_rijbaan_regionale_weg bgt parkeerscans
#

#echo "Load buurt / buurtcombinatie"
dc exec -T database update-table.sh bag bag_buurt public parkeerscans
#

#echo "create wegdelen / buurten and complete the scans data"
dc run --rm importer ./docker-wegdelen.sh
#

echo "create occupancy tables and views"
dc run --rm importer ./docker-occupancy-bakker.sh


# run the DB backup shizzle
dc exec -T database ./backup-db-occupancy.sh


dc down --remove-orphans
echo "DONE! with OCCUPATION data import. You are awesome! <3"
