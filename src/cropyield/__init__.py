"""Smallholder maize-yield estimation from Sentinel-2 (DSC 291).

One subpackage per pipeline stage:
    data       cohorts, season windows, the labels table
    satellite  Sentinel-2 search, pixel reads, cloud masks, monthly composites
    features   seasonal indices, MOSAIKS features, Presto tensors
    models     baselines, GRU, frozen and fine-tuned Presto, photo model
    eval       splits, metrics, noise ceilings, targeting metrics, PPI
See docs/STRUCTURE.md.
"""
