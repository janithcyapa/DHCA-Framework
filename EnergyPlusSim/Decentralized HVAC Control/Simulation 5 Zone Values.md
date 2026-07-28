
### Calculated Expected Values

| **Zone**     | **αext​ (x8​)** | **αint​ (x9​)** | **βair​ (x10​)** | **βmass​ (x11​)** |
| ------------ | --------------- | --------------- | ---------------- | ----------------- |
| **PLENUM-1** | 3506.576        | 2500.000        | 2.915e-06        | 2.157e-08         |
| **SPACE1-1** | 232.558         | 588.235         | 3.451e-06        | 1.008e-07         |
| **SPACE2-1** | 114.943         | 256.410         | 7.991e-06        | 2.340e-07         |
| **SPACE3-1** | 232.558         | 588.235         | 3.451e-06        | 1.036e-07         |
| **SPACE4-1** | 114.943         | 256.410         | 7.991e-06        | 2.340e-07         |
| **SPACE5-1** | 0.001           | 1111.111        | 1.844e-06        | 5.480e-08         |

ccording to the Colombo/Katunayake weather data you provided, here are the best options to consider:

- **For Peak Cooling Loads (May):** The weather file explicitly designates May as the "Hottest Month". Furthermore, it identifies the period from May 7th to May 13th as an "Extreme" week near the annual maximum. This is the best month to test how well your custom controller handles maximum thermal stress and peak cooling demands.
    
- **For Baseline Performance (March):** The data highlights March 12th to March 18th as a "Typical" week that reflects the near-average annual conditions. Running your simulation in March will give you the most accurate representation of everyday efficiency and standard day-to-day operations.
    
- **For Minimum Loads (November / December):** December is classified as the "Coldest Month". Additionally, an "Extreme" week near the annual minimum is noted between November 19th and November 25th. Testing during these milder periods is a great way to ensure your controller doesn't over-cool the building or short-cycle.