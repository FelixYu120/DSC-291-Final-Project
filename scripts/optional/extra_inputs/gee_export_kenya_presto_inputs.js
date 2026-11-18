/*
Earth Engine export for Kenya OAF 2019-2020 extra inputs.

Upload upload/kenya_fields_2019_2020.csv as a point table using lon and lat,
then use the asset ID below. Six small exports avoid the concurrent-
aggregation error encountered in the Zimbabwe run.
*/

var FIELD_ASSET = 'projects/dsc190-crop-yield/assets/kenya_fields_2019_2020';
var DRIVE_FOLDER = 'DSC291_Kenya_Presto';
var fields = ee.FeatureCollection(FIELD_ASSET);
var allRegion = fields.geometry().bounds();

var s1Base = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(allRegion)
  .filterDate('2019-01-01', '2020-11-01')
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'));

function s1ForMonth(start, passName, suffix) {
  var end = start.advance(1, 'month');
  var mid = start.advance(end.difference(start, 'day').divide(2), 'day');
  var collection = s1Base
    .filterDate(start.advance(-45, 'day'), end.advance(45, 'day'))
    .filter(ee.Filter.eq('orbitProperties_pass', passName))
    .map(function(image) {
      return image.set('dateDist', ee.Number(image.get('system:time_start')).subtract(mid.millis()).abs());
    })
    .sort('dateDist');
  var closest = ee.Number(collection.first().get('dateDist'));
  var maxDiff = closest.max(15 * 24 * 60 * 60 * 1000);
  var kept = collection.filter(ee.Filter.lte('dateDist', maxDiff));
  var raw = kept.select(['VV', 'VH']).median();
  var median3 = raw.focalMedian({radius: 1, units: 'pixels'});
  var count = kept.select('VV').count();
  return raw.rename(['VV_' + suffix + '_point', 'VH_' + suffix + '_point'])
    .addBands(median3.rename(['VV_' + suffix + '_median3', 'VH_' + suffix + '_median3']))
    .addBands(count.rename('s1_' + suffix + '_count'));
}

function imageForMonth(monthString, seasonYear) {
  var start = ee.Date(ee.String(monthString).cat('-01'));
  var chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
    .filterDate(start, start.advance(1, 'month'))
    .sum().rename('chirps_precip_mm');
  var era = ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR')
    .filterDate(start, start.advance(1, 'month')).first()
    .select(['temperature_2m', 'total_precipitation_sum'])
    .rename(['temperature_2m', 'total_precipitation']);
  var elevation = ee.Image('USGS/SRTMGL1_003').select('elevation');
  var slope = ee.Terrain.slope(elevation).rename('slope');
  var alphaEarth = ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL')
    .filterDate(ee.Date.fromYMD(seasonYear, 1, 1), ee.Date.fromYMD(ee.Number(seasonYear).add(1), 1, 1))
    .filterBounds(allRegion).mosaic().select('A.*');
  var raw = s1ForMonth(start, 'ASCENDING', 'asc')
    .addBands(s1ForMonth(start, 'DESCENDING', 'desc'))
    .addBands(era).addBands(chirps).addBands(elevation).addBands(slope).addBands(alphaEarth);
  var norm = raw.select('VV_.*').add(25).divide(25)
    .addBands(raw.select('VH_.*').add(25).divide(25))
    .addBands(raw.select('temperature_2m').subtract(272.15).divide(35).rename('temperature_2m_presto'))
    .addBands(raw.select('total_precipitation').divide(0.03).rename('total_precipitation_presto'))
    .addBands(raw.select('elevation').divide(2000).rename('elevation_presto'))
    .addBands(raw.select('slope').divide(50).rename('slope_presto'));
  var normNames = norm.bandNames().map(function(name) {
    name = ee.String(name);
    return ee.Algorithms.If(name.match('^(VV|VH)_').length(), name.cat('_presto'), name);
  });
  return raw.addBands(norm.rename(normNames)).unmask(-9999);
}

function outputForBatch(batch) {
  var seasonFields = fields.filter(ee.Filter.eq('season_year', batch.year));
  return ee.FeatureCollection(ee.List(batch.months).map(function(monthString) {
    monthString = ee.String(monthString);
    var monthFields = seasonFields.map(function(feature) { return feature.set('month', monthString); });
    return imageForMonth(monthString, batch.year).sampleRegions({
      collection: monthFields,
      properties: ['obs_id', 'cohort', 'season_year', 'month', 'lat', 'lon'],
      scale: 10,
      geometries: false,
      tileScale: 4
    });
  })).flatten();
}

var batches = [
  {name: 'part1_s2019_feb_apr', year: 2019, months: ['2019-02', '2019-03', '2019-04']},
  {name: 'part2_s2019_may_jul', year: 2019, months: ['2019-05', '2019-06', '2019-07']},
  {name: 'part3_s2019_aug_sep', year: 2019, months: ['2019-08', '2019-09']},
  {name: 'part4_s2020_feb_apr', year: 2020, months: ['2020-02', '2020-03', '2020-04']},
  {name: 'part5_s2020_may_jul', year: 2020, months: ['2020-05', '2020-06', '2020-07']},
  {name: 'part6_s2020_aug_sep', year: 2020, months: ['2020-08', '2020-09']}
];

print('Kenya fields', fields.size());
print('Expected rows across all exports', 31816);
batches.forEach(function(batch) {
  var prefix = 'kenya_presto_s1_era5_srtm_2019_2020_' + batch.name;
  Export.table.toDrive({
    collection: outputForBatch(batch),
    description: prefix,
    folder: DRIVE_FOLDER,
    fileNamePrefix: prefix,
    fileFormat: 'CSV'
  });
});
