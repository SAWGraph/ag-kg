## Soil Map Unit, Component, Horizon, and Observation Mapping

The generated RDF represents soil information using the following hierarchy:

```text
S2 Cell
  └── sosa:isFeatureOfInterestOf
        SoilMapUnitS2OverlapObservation
          ├── kwg-ont:observedOverlapWith → SoilMapUnit
          ├── sosa:observedProperty → kwgr:s2OverlapObservableProperty.soilMapUnitOverlapArea
          └── sosa:hasSimpleResult → overlap area


SoilMapUnit
  ├── kwg-ont:soilMapUnitName → map unit name
  ├── kwg-ont:soilMapUnitSymbol → map unit symbol
  ├── kwg-ont:soilMapUnitKey → mukey
  │
  ├── sosa:isFeatureOfInterestOf
  │       SoilMapUnitObservationCollection
  │         └── sosa:hasMember → SoilMapUnitObservation
  │
  └── ag:hasSoilComponent
          SoilComponent
            ├── ag:soilComponentKey → cokey
            ├── ag:soilComponentName → compname
            ├── ag:componentAreaPercentage → comppct_r
            │
            └── ag:hasSoilHorizon
                    SoilHorizon
                      ├── ag:soilHorizonKey → chkey
                      ├── ag:soilHorizonName → hzname
                      ├── ag:soilHorizonTopDepthCm → hzdept_r
                      ├── ag:soilHorizonBottomDepthCm → hzdepb_r
                      │
                      └── SoilMapUnitObservation
                            ├── sosa:hasFeatureOfInterest → SoilHorizon
                            ├── sosa:observedProperty → agr:soilObservableProperty.*
                            └── sosa:hasSimpleResult → property value
