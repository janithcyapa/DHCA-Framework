
OS:Version,
  {c945c26e-8c22-47e9-a537-7d7a629f80e6}, !- Handle
  3.10.0;                                 !- Version Identifier

OS:Site,
  {f8b9c944-73ac-4e76-9a56-0b3be384a00c}, !- Handle
  Site 1,                                 !- Name
  ,                                       !- Latitude {deg}
  ,                                       !- Longitude {deg}
  ,                                       !- Time Zone {hr}
  ,                                       !- Elevation {m}
  ;                                       !- Terrain

OS:YearDescription,
  {cd0b02c9-ae4b-4d27-836a-c74fa6c0f715}; !- Handle

OS:ClimateZones,
  {63b8c045-24bd-45cd-a724-f2d8248b6d56}, !- Handle
  ASHRAE,                                 !- Climate Zone Institution Name 1
  ANSI/ASHRAE Standard 169,               !- Climate Zone Document Name 1
  2006,                                   !- Climate Zone Document Year 1
  ,                                       !- Climate Zone Value 1
  CEC,                                    !- Climate Zone Institution Name 2
  California Climate Zone Descriptions,   !- Climate Zone Document Name 2
  1995,                                   !- Climate Zone Document Year 2
  ;                                       !- Climate Zone Value 2

OS:Building,
  {0517ff98-8305-4b96-8fa3-db7fdecfb8dd}, !- Handle
  Building 1,                             !- Name
  ,                                       !- Building Sector Type
  ,                                       !- North Axis {deg}
  ,                                       !- Nominal Floor to Floor Height {m}
  ,                                       !- Space Type Name
  ,                                       !- Default Construction Set Name
  ;                                       !- Default Schedule Set Name

OS:Facility,
  {9b25f6c2-2fd9-49c7-8ffd-5d47df7d91f5}; !- Handle

OS:SimulationControl,
  {bbf3829d-b628-4f90-b758-aed79363a74e}; !- Handle

OS:Sizing:Parameters,
  {2a096977-99c6-4e37-90f2-d05257621b69}, !- Handle
  1.25,                                   !- Heating Sizing Factor
  1.15;                                   !- Cooling Sizing Factor

OS:Timestep,
  {b2ee27c3-e73b-467a-abb0-8de6b7a724a2}, !- Handle
  6;                                      !- Number of Timesteps per Hour

OS:ShadowCalculation,
  {3e2d8c4d-807c-4622-9a3c-743beeb22265}, !- Handle
  PolygonClipping,                        !- Shading Calculation Method
  ,                                       !- Shading Calculation Update Frequency Method
  20,                                     !- Shading Calculation Update Frequency
  15000,                                  !- Maximum Figures in Shadow Overlap Calculations
  ,                                       !- Polygon Clipping Algorithm
  512,                                    !- Pixel Counting Resolution
  ,                                       !- Sky Diffuse Modeling Algorithm
  No,                                     !- Output External Shading Calculation Results
  No,                                     !- Disable Self-Shading Within Shading Zone Groups
  No;                                     !- Disable Self-Shading From Shading Zone Groups to Other Zones

OS:HeatBalanceAlgorithm,
  {d1d39280-c749-41d0-890b-e47cde0b14b2}, !- Handle
  ConductionTransferFunction,             !- Algorithm
  200;                                    !- Surface Temperature Upper Limit {C}

OS:RunPeriod,
  {1c519356-caac-46cd-8053-730dc9165b13}, !- Handle
  Run Period 1,                           !- Name
  1,                                      !- Begin Month
  1,                                      !- Begin Day of Month
  12,                                     !- End Month
  31,                                     !- End Day of Month
  ,                                       !- Use Weather File Holidays and Special Days
  ,                                       !- Use Weather File Daylight Saving Period
  ,                                       !- Apply Weekend Holiday Rule
  ,                                       !- Use Weather File Rain Indicators
  ,                                       !- Use Weather File Snow Indicators
  ;                                       !- Number of Times Runperiod to be Repeated

OS:LifeCycleCost:Parameters,
  {8025bbb4-bff8-421c-9bfa-3e4bda4639d7}, !- Handle
  ,                                       !- Analysis Type
  ,                                       !- Discounting Convention
  ,                                       !- Inflation Approach
  ,                                       !- Real Discount Rate
  ,                                       !- Nominal Discount Rate
  ,                                       !- Inflation
  ,                                       !- Base Date Month
  ,                                       !- Base Date Year
  ,                                       !- Service Date Month
  ,                                       !- Service Date Year
  ;                                       !- Length of Study Period in Years

