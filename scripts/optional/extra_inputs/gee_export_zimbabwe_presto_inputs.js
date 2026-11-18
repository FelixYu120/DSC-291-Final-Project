/*
Earth Engine handoff: Zimbabwe Presto inputs for the 2022 and 2023 seasons.

Before running, upload derived/zimbabwe_field_months_2022_2023.csv as an Earth
Engine table and replace FIELD_MONTH_ASSET below.  Ensure the import creates
point geometries from longitude and latitude.

The export contains one row per obs_id x month.  Sentinel-1 is exported for
both orbit directions; the local integration script chooses one consistent
direction per observation.  Missing values are -9999 and have explicit count
columns.  Raw and Presto-normalized values are both exported.
*/

var FIELD_MONTH_ASSET = 'projects/dsc190-crop-yield/assets/zimbabwe_field_months_2022_2023';
var DRIVE_FOLDER = 'DSC291_Zimbabwe_Presto';

var fields = ee.FeatureCollection(FIELD_MONTH_ASSET);
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
    .filter(ee.Filter.eq('orbitProperties_pass', passName))
    .map(function(image) {
      return image.set(
        'dateDist',
        ee.Number(image.get('system:time_start')).subtract(mid.millis()).abs()
      );
    })
    .sort('dateDist');

  // Matches OpenMapFlow/Presto: use all scenes within 15 days of the midpoint;
  // if none exists, use the closest scene(s).
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
  monthString = ee.String(monthString);
  seasonYear = ee.Number(seasonYear);
  var start = ee.Date(monthString.cat('-01'));
  var era = ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR')
    .filterDate(start, start.advance(1, 'month'))
    .first()
    .select(['temperature_2m', 'total_precipitation_sum'])
    .rename(['temperature_2m', 'total_precipitation']);

  var elevation = ee.Image('USGS/SRTMGL1_003').select('elevation');
  var slope = ee.Terrain.slope(elevation).rename('slope');
  var alphaEarth = ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL')
    .filterDate(ee.Date.fromYMD(seasonYear, 1, 1), ee.Date.fromYMD(seasonYear.add(1), 1, 1))
    .filterBounds(allRegion)
    .mosaic()
    .select('A.*');
  var raw = s1ForMonth(start, 'ASCENDING', 'asc')
    .addBands(s1ForMonth(start, 'DESCENDING', 'desc'))
    .addBands(era)
    .addBands(elevation)
    .addBands(slope)
    .addBands(alphaEarth);

  // Exact normalization constants from Presto's official pipeline.
  var norm = raw.select('VV_.*').add(25).divide(25)
    .addBands(raw.select('VH_.*').add(25).divide(25))
    .addBands(raw.select('temperature_2m').add(-272.15).divide(35)
      .rename('temperature_2m_presto'))
    .addBands(raw.select('total_precipitation').divide(0.03)
      .rename('total_precipitation_presto'))
    .addBands(raw.select('elevation').divide(2000).rename('elevation_presto'))
    .addBands(raw.select('slope').divide(50).rename('slope_presto'));

  // Give normalized radar bands unambiguous names.
  var normNames = norm.bandNames().map(function(name) {
    name = ee.String(name);
    return ee.Algorithms.If(
      name.match('^(VV|VH)_').length(), name.cat('_presto'), name
    );
  });
  norm = norm.rename(normNames);
  return raw.addBands(norm).unmask(-9999);
}

function outputForMonths(months, seasonYear) {
  return ee.FeatureCollection(ee.List(months).map(function(monthString) {
    monthString = ee.String(monthString);
    var monthFields = fields.filter(ee.Filter.eq('month', monthString));
    return imageForMonth(monthString, seasonYear).sampleRegions({
      collection: monthFields,
      properties: ['obs_id', 'season_year', 'month', 'latitude', 'longitude'],
      scale: 10,
      geometries: false,
      tileScale: 4
    });
  })).flatten();
}

// Six smaller jobs avoid Earth Engine's concurrent-aggregation limit. Each
// job contains three months; together they still produce exactly 20,394 rows.
var batches = [
  {name: 'part1_s2022_oct_dec', year: 2022, months: ['2021-10', '2021-11', '2021-12']},
  {name: 'part2_s2022_jan_mar', year: 2022, months: ['2022-01', '2022-02', '2022-03']},
  {name: 'part3_s2022_apr_jun', year: 2022, months: ['2022-04', '2022-05', '2022-06']},
  {name: 'part4_s2023_oct_dec', year: 2023, months: ['2022-10', '2022-11', '2022-12']},
  {name: 'part5_s2023_jan_mar', year: 2023, months: ['2023-01', '2023-02', '2023-03']},
  {name: 'part6_s2023_apr_jun', year: 2023, months: ['2023-04', '2023-05', '2023-06']}
];

print('Expected total rows across all six exports', fields.size());
print('Six export tasks created. Start all six in the Tasks tab.');

batches.forEach(function(batch) {
  var prefix = 'zimbabwe_presto_s1_era5_srtm_2022_2023_' + batch.name;
  Export.table.toDrive({
    collection: outputForMonths(batch.months, batch.year),
    description: prefix,
    folder: DRIVE_FOLDER,
    fileNamePrefix: prefix,
    fileFormat: 'CSV'
  });
});
