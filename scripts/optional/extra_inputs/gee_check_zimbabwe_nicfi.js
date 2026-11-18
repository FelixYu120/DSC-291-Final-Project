/* Optional Planet NICFI coverage check. Run only after Planet/NICFI access is approved. */

var FIELD_MONTH_ASSET = 'projects/dsc190-crop-yield/assets/zimbabwe_field_months_2022_2023';
var fields = ee.FeatureCollection(FIELD_MONTH_ASSET);
var months = ee.List(fields.aggregate_array('month')).distinct().sort();
var nicfi = ee.ImageCollection('projects/planet-nicfi/assets/basemaps/africa')
  .filter(ee.Filter.eq('cadence', 'monthly'));

var coverage = ee.FeatureCollection(months.map(function(monthString) {
  monthString = ee.String(monthString);
  var start = ee.Date(monthString.cat('-01'));
  var monthly = nicfi.filterDate(start, start.advance(1, 'month')).mosaic();
  var valid = monthly.select('R').mask().rename('nicfi_valid').unmask(0);
  return valid.sampleRegions({
    collection: fields.filter(ee.Filter.eq('month', monthString)),
    properties: ['obs_id', 'season_year', 'month', 'latitude', 'longitude'],
    scale: 4.77,
    geometries: false,
    tileScale: 4
  });
})).flatten();

print('Expected rows', fields.size());
print('Coverage rows', coverage.size());
print('Valid rows', coverage.filter(ee.Filter.eq('nicfi_valid', 1)).size());

Export.table.toDrive({
  collection: coverage,
  description: 'zimbabwe_nicfi_coverage_2022_2023',
  folder: 'DSC291_Zimbabwe_Presto',
  fileNamePrefix: 'zimbabwe_nicfi_coverage_2022_2023',
  fileFormat: 'CSV'
});
