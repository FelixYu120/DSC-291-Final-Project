/*
Earth Engine export for Malawi 2022-2023 extra inputs.

Upload upload/malawi_fields_2022_2023.geojson without replacing its polygon
geometry. Each output row is the median of the 10 m pixel centres inside one
field polygon. Six small tasks avoid the concurrent-aggregation limit.
*/

var FIELD_ASSET = 'projects/dsc190-crop-yield/assets/malawi_fields_2022_2023';
var DRIVE_FOLDER = 'DSC291_Malawi_Presto';
// ESRI Shapefile DBF names are limited to ten characters, so the upload file
// stores season_year as season_yr. Restore the canonical name immediately.
var fields = ee.FeatureCollection(FIELD_ASSET).map(function(feature) {
  return feature.set('season_year', feature.get('season_yr'));
});
var allRegion = fields.geometry().bounds();

var s1Base = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(allRegion)
  .filterDate('2021-09-01', '2023-08-01')
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
  var count = kept.select('VV').count();
  return raw.rename(['VV_' + suffix, 'VH_' + suffix])
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
    .filterDate(
      ee.Date.fromYMD(seasonYear, 1, 1),
      ee.Date.fromYMD(ee.Number(seasonYear).add(1), 1, 1)
    )
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
    var monthFields = seasonFields.map(function(feature) {
      return feature.set('month', monthString);
    });
    return imageForMonth(monthString, batch.year).reduceRegions({
      collection: monthFields,
      reducer: ee.Reducer.median(),
      scale: 10,
      tileScale: 4
    }).map(function(feature) {
      return feature.setGeometry(null);
    });
  })).flatten();
}

var batches = [
  {name: 'part1_s2022_oct_dec', year: 2022, months: ['2021-10', '2021-11', '2021-12']},
  {name: 'part2_s2022_jan_mar', year: 2022, months: ['2022-01', '2022-02', '2022-03']},
  {name: 'part3_s2022_apr_jun', year: 2022, months: ['2022-04', '2022-05', '2022-06']},
  {name: 'part4_s2023_oct_dec', year: 2023, months: ['2022-10', '2022-11', '2022-12']},
  {name: 'part5_s2023_jan_mar', year: 2023, months: ['2023-01', '2023-02', '2023-03']},
  {name: 'part6_s2023_apr_jun', year: 2023, months: ['2023-04', '2023-05', '2023-06']}
];

print('Malawi polygons', fields.size());
print('Expected rows across all exports', 7101);
batches.forEach(function(batch) {
  var prefix = 'malawi_presto_s1_era5_srtm_2022_2023_' + batch.name;
  Export.table.toDrive({
    collection: outputForBatch(batch),
    description: prefix,
    folder: DRIVE_FOLDER,
    fileNamePrefix: prefix,
    fileFormat: 'CSV'
  });
});
