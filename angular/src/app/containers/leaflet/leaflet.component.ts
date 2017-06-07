import {
  AfterViewInit,
  Component,
  ElementRef,
  NgZone
} from '@angular/core';
import { Store } from '@ngrx/store';
import { Observable } from 'rxjs/Rx';
import 'rxjs/add/operator/map';
import L from 'leaflet';
import 'leaflet-choropleth';
import { config } from './leaflet.component.config';
import { Parkeerkans } from '../../models/parkeerkans';
import { State } from '../../reducers';
import { getMapSelection } from '../../reducers';
import { MapCrs } from '../../services/map-crs';
import { ParkeerkansService } from '../../services/parkeerkans';
import { WegdelenService } from '../../services/wegdelen';
import { ParkeervakkenService } from '../../services/parkeervakken';

@Component({
  selector: 'dp-leaflet',
  template: '',
  styleUrls: [
    './leaflet.scss'
  ]
})
export class LeafletComponent implements AfterViewInit {
  private leafletMap: L.Map;
  private selection$: Observable<any>;
  private occupation: {[wegdeelId: string]: number};
  private day;
  private daygte;
  private daylte;
  private hour;
  private hourlte;
  private hourgte;
  private year;
  private month;

  constructor(
    private crs: MapCrs,
    private host: ElementRef,
    private parkeerkansService: ParkeerkansService,
    private parkeervakkenService: ParkeervakkenService,
    private store: Store<State>,
    private wegdelenService: WegdelenService,
    private zone: NgZone) {

    this.selection$ = store.select(getMapSelection);
  }

  public ngAfterViewInit() {
    this.initLeaflet();
    this.updateBoundingBox();
    this.selection$.forEach((payload) => {
      if (payload) {
        this.day = payload.day;
        this.daygte = payload.daygte;
        this.daylte = payload.daylte;
        this.hour = payload.hour;
        this.hourgte = payload.hourgte;
        this.hourlte = payload.hourlte;
        this.year = payload.year;
        this.month = payload.month;
        this.updateBoundingBox();
      }
    });
  }

  private initLeaflet() {
    this.zone.run(() => {
      const options = Object.assign({}, config.map, {
        crs: this.crs.getRd()
      });
      this.leafletMap = L.map(this.host.nativeElement, options)
        .setView([52.3731081, 4.8932945], 11);
      const baseLayer = L.tileLayer('https://{s}.data.amsterdam.nl/topo_rd_zw/{z}/{x}/{y}.png', {
        subdomains: ['acc.t1', 'acc.t2', 'acc.t3', 'acc.t4'],
        tms: true,
        minZoom: 8,
        maxZoom: 16,
        bounds: config.map.maxBounds
      });

      baseLayer.addTo(this.leafletMap);

      setTimeout(() => {
        this.leafletMap.invalidateSize();
      });

      this.leafletMap.on('moveend', this.updateBoundingBox.bind(this));
      this.leafletMap.on('zoomend', this.updateBoundingBox.bind(this));
    });
  }

  private updateBoundingBox() {
    const boundingBox = this.leafletMap.getBounds().toBBoxString();
    Observable
      .zip(
      this.parkeerkansService.getParkeerkans(
      	boundingBox,
	this.day,
	this.daygte,
	this.daylte,
	this.hour,
	this.hourgte,
	this.hourlte,
	this.year,
	this.month),
        this.wegdelenService.getWegdelen(boundingBox))
      .subscribe(this.showWegdelen.bind(this), this.showError);
  }

  private showWegdelen([parkeerkans, wegdelen]: [Parkeerkans, any]) {
    this.occupation = {};
    const data = wegdelen.map((wegdeel) => {
      const wegdeelKans = parkeerkans.wegdelen[wegdeel.properties.id];
      wegdeel.properties.bezetting = wegdeelKans ? wegdeelKans.occupation : undefined;
      this.occupation[wegdeel.properties.id] = wegdeel.properties.bezetting;
      return wegdeel;
    }).filter((wegdeel) => {
      return wegdeel.properties.bezetting === 'fout' ? false
        : wegdeel.properties.bezetting !== undefined;
    });

    // Add entries with a bezetting of 0 and 100 to make sure choropleth takes the full percentage
    // range as the range for it's colors.
    data.push({ properties: { bezetting: 0 } });
    data.push({ properties: { bezetting: 100 } });

    L.choropleth({
      type: 'FeatureCollection',
      features: data
    }, config.choropleth.wegdelen).addTo(this.leafletMap);

    const boundingBox = this.leafletMap.getBounds().toBBoxString();
    this.parkeervakkenService.getVakken(boundingBox)
      .subscribe(this.showParkeervakken.bind(this), this.showError);
  }

  private showParkeervakken(parkeervakken) {
    const that = this;
    parkeervakken = parkeervakken.map((parkeervak) => {
      parkeervak.properties.bezetting = that.occupation[parkeervak.properties.bgt_wegdeel];
      return parkeervak;
    }).filter((parkeervak) => {
      return parkeervak.properties.bezetting !== undefined;
    });

    parkeervakken.push({ properties: { bezetting: 0 } });
    parkeervakken.push({ properties: { bezetting: 100 } });

    L.choropleth({
      type: 'FeatureCollection',
      features: parkeervakken
    }, config.choropleth.parkeervakken).addTo(this.leafletMap);
  }

  private showError(error) {
    console.error(error);
  }
}
