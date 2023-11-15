from flask import Flask, render_template, request
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


app = Flask(__name__)

# Simplified data processing function
def read_data(start_week, end_week):
    data = pd.DataFrame()

    for week in range(start_week, end_week + 1):
        temp_df = pd.read_excel("RB_Data.xlsx", sheet_name=f"Week{week}")

        # Preprocess: Drop irrelevant columns and convert data types
        temp_df.drop(['FL', 'ROST'], axis=1, inplace=True)
        convert = temp_df.select_dtypes('object').columns.difference(['Player'])
        temp_df[convert] = temp_df[convert].apply(lambda x: pd.to_numeric(x.str.replace(',', ''), errors='coerce')).fillna(0)
        temp_df['Rank'] = temp_df['Rank'].astype('Int64')

        # Group by 'Player' and aggregate data
        if data.empty:
            data = temp_df
        else:
            data = data.merge(temp_df, on='Player', suffixes=('', '_week' + str(week)))

    # Apply custom aggregation logic
    for column in data.columns:
        if column.endswith(tuple([f'_week{week}' for week in range(start_week + 1, end_week + 1)])):
            base_column = column.split('_week')[0]
            if base_column in ['Rank', 'Player']:  # Take the latest value
                data[base_column] = data[column]
            elif base_column in ['LG']:  # Take the maximum value
                data[base_column] = data[[base_column, column]].max(axis=1)
            else:  # Sum the values
                data[base_column] += data[column]
            data.drop(column, axis=1, inplace=True)  # Drop the extra week column

    # Calculate 'Y/A' and 'Y/R' based on summed values
    data['Y/A'] = (data['YDS'] / data['ATT']).round(1)
    data['Y/R'] = (data['YDS.1'] / data['REC']).round(1)
    data['FPTS/G'] = (data['FPTS'] / data['G']).round(1)

    return data

def calculate_per_game_stats(df):
    per_game = list(df.columns[2:])
    exclude_per_game = ['Y/A', 'LG', 'Y/R', 'G', 'FPTS', 'FPTS/G', 'Weeks']

    for col in per_game:
        if col not in exclude_per_game:
            df[col + '/game'] = (df[col] / df['G']).round(1)
    
    final_columns = exclude_per_game + [col + '/game' for col in per_game if col not in exclude_per_game]
    return df, final_columns

def calculate_correlations(df, final_columns):
    exclude_corr = ['FPTS/G', 'FPTS', 'G', 'Weeks']
    corr_columns = [col for col in final_columns if col not in exclude_corr]

    def compute_correlations(dataframe, corr_columns):
        return dataframe[corr_columns].corrwith(dataframe['FPTS/G'])

    corr_all = compute_correlations(df, corr_columns)
    corr_nonzero = compute_correlations(df[df['FPTS/G'] > 0], corr_columns)
    corr_top50 = compute_correlations(df[df['Rank'] <= 50], corr_columns)
    corr_top25 = compute_correlations(df[df['Rank'] <= 25], corr_columns)

    df_corr = pd.DataFrame({
        'All Players': corr_all,
        'FPTS > 0': corr_nonzero,
        'Top 50 Players': corr_top50,
        'Top 25 Players': corr_top25
    })
    df_corr['Correlation'] = df_corr.mean(axis=1)
    df_corr['R^2'] = df_corr['Correlation'] ** 2

    return df_corr, corr_columns

def final_analysis(df, df_corr, corr_columns):
    def weight_calc(row):
        if row['Correlation'] >= 0.69:
            return 1 + row['R^2']
        else:
            return 1

    df_corr['Weight'] = df_corr.apply(weight_calc, axis=1)

    for col in corr_columns:
        weight = df_corr.loc[col, 'Weight']
        df[col + '_weighted'] = (df[col] * weight).round(1)

    weight_columns = [col + '_weighted' for col in corr_columns]
    high_corr = df_corr[df_corr['Correlation'] >= 0.69].index.tolist()
    conditional_columns = [col + '_weighted' for col in high_corr if col + '_weighted' in df.columns]
    conditional_columns.append('FPTS/G')

    avg = ['ATT/game_weighted', 'YDS/game_weighted', 'TD/game_weighted', 'REC/game_weighted', 'TGT/game_weighted', 'YDS.1/game_weighted', 'FPTS/G']
    df['Score'] = df[avg].mean(axis=1).round(1)
    df['Final Rank'] = df.sort_values('Score', ascending=False)['Score'].rank(method='first', ascending=False, na_option='bottom').astype(int)
    df['Variance'] = df['Rank'] - df['Final Rank']
    analysis = df[['Rank', 'Final Rank', 'Player', 'Score', 'Variance'] + conditional_columns]

    return analysis

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        start_week = int(request.form['start_week'])
        end_week = int(request.form['end_week'])
        
        # Ensure df is defined here by calling read_data
        df = read_data(start_week, end_week)

        # Now df is defined, proceed with the rest of the process
        df, final_columns = calculate_per_game_stats(df)
        df_corr, corr_columns = calculate_correlations(df, final_columns)
        final_data = final_analysis(df, df_corr, corr_columns)

        # Convert final data to HTML for display
        final_table = final_data.to_html()
        return render_template('results.html', table=final_table)
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
