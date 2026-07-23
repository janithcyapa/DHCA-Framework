energyplus -w weather.epw -d ./baseline_results 5ZoneAutoDXVAV.idf

python dashboard.py

python dashboard.py -s 

python dashboard.py --live

cat ./baseline_results/eplusout.err

lsof -i :8050
kill -9 730518


energyplus -w weather.epw -d ./baseline_results 5ZoneAutoDXVAV.idf && python plot.py