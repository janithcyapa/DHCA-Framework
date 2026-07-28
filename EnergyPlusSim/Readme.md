#### Switch to Sri Lanka
./switch_weather.sh colombo

#### Switch back to Chicago
./switch_weather.sh chicago

#### See current active weather
./switch_weather.sh

#### Then run simulation as normal
energyplus -w weather.epw -d ./results 5ZoneAutoDXVAV.idf


#### Bench mark
USE_CUSTOM_CONTROLLERS=0 energyplus -w weather.epw -d ./results 5ZoneAutoDXVAV.idf

python summary.py

fuser -k 8050/tcp

python dashboard.py

python dashboard.py -s 

python dashboard.py --live

cat ./baseline_results/eplusout.err

lsof -i :8050
kill -9 730518


energyplus -w weather.epw -d ./baseline_results 5ZoneAutoDXVAV.idf && python plot.py