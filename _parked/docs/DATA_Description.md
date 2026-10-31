For one field, the steps are:

    Label: it gives the place (lat/lon, or a polygon in Malawi) and the season, for example Feb–Sep 2020.

    Catalogue: we ask which Sentinel-2 images cover this place in this season. We get a list of images with their links.

    One image per month: we use the cloud map to find a clear image for each month.
    Position: we change lat/lon into a pixel position in that image. Around it we mark a 64 × 64 pixel window.
    
    Fetch: the image has 11 separate files, one per band plus the cloud map. From each file we fetch only the block that holds our window.
    Cut and save: we cut the 64 × 64 window from each block, save it, and throw away the rest.