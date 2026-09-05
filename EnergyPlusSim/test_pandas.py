import pandas as pd
df = pd.read_csv('./results/state_log.csv')
print(df['Hour'].describe())
print(df[df['Hour'] > 24][['DayOfYear', 'Hour', 'Minute']])
try:
    df['Datetime'] = pd.Timestamp(year=2014, month=1, day=1) + \
                     pd.to_timedelta(df['DayOfYear'] - 1, unit='D') + \
                     pd.to_timedelta(df['Hour'], unit='h') + \
                     pd.to_timedelta(df['Minute'], unit='m')
except Exception as e:
    import traceback
    traceback.print_exc()
