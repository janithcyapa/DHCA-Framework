energyplus -w weather.epw -d ./baseline_results 5ZoneAutoDXVAV.idf


python plot.py
cat ./baseline_results/eplusout.err


energyplus -w weather.epw -d ./baseline_results 5ZoneAutoDXVAV.idf && python plot.py