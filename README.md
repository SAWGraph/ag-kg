## Soil Map Unit, Component, Horizon, and Observation Mapping

The generated RDF represents soil information using the following hierarchy:

```text
S2 Cell
  └── sosa:isFeatureOfInterestOf
        kwg-ont:SoilMapUnitS2OverlapObservation
          ├── kwg-ont:observedOverlapWith → kwg-ont:SoilMapUnit
          ├── sosa:observedProperty → kwgr:s2OverlapObservableProperty.soilMapUnitOverlapArea
          └── sosa:hasSimpleResult → overlap area


kwg-ont:SoilMapUnit
  ├── kwg-ont:soilMapUnitName → mu.muname
  ├── kwg-ont:soilMapUnitSymbol → mu.musym
  ├── kwg-ont:soilMapUnitKey → mu.mukey
  ├── kwg-ont:soilSurveyArea → kwgr:soilSurveyArea.<lkey>
  │
  └── ag:hasSoilComponent
        ag:SoilComponent
          ├── ag:soilComponentKey → c.cokey
          ├── ag:soilComponentName → c.compname
          ├── ag:componentAreaPercentage → c.comppct_r
          │
          └── ag:hasSoilHorizon
                ag:SoilHorizon
                  ├── ag:soilHorizonKey → hz.chkey
                  ├── ag:soilHorizonName → hz.hzname
                  ├── ag:soilHorizonTopDepthCm → hz.hzdept_r
                  ├── ag:soilHorizonBottomDepthCm → hz.hzdepb_r
                  │
                  └── sosa:isFeatureOfInterestOf
                        ag:SoilHorizonObservationCollection
                          ├── sosa:hasFeatureOfInterest → ag:SoilHorizon
                          └── sosa:hasMember
                                ag:SoilHorizonObservation
                                  ├── sosa:observedProperty → ag:soilObservableProperty.*
                                  └── sosa:hasSimpleResult → value
