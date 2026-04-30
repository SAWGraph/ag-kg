## Soil Map Unit, Component, Horizon, and Observation Mapping

The generated RDF represents soil information using the following hierarchy:

```text
S2 Cell
  └── sosa:isFeatureOfInterestOf
        SoilMapUnitS2OverlapObservation
          ├── kwg-ont:observedOverlapWith → SoilMapUnit
          ├── sosa:observedProperty → s2OverlapObservableProperty.soilMapUnitOverlapArea
          └── sosa:hasSimpleResult → overlap area

SoilMapUnit
  ├── kwg-ont:hasSoilComponent → SoilComponent
  │     └── kwg-ont:hasSoilHorizon → SoilHorizon
  │            └── sosa:isFeatureOfInterestOf / reverse of sosa:hasFeatureOfInterest
  │                  SoilMapUnitObservation
  │                    ├── sosa:observedProperty → om_r / cec7_r / ph1to1h2o_r / texture
  │                    └── sosa:hasSimpleResult → value
  │
  └── sosa:isFeatureOfInterestOf → SoilMapUnitObservationCollection
        └── sosa:hasMember → SoilMapUnitObservation
