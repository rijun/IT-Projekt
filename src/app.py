"""
This script runs a flask server.

Requirements: flask

Usage:  @app.route('/foo') creates an API endpoint to which an GET/POST request can be sent, e.g. http://bar.com/foo
        Request arguments can be accessed by: request.args["<request_variable_name>"]
"""
# TODO: Refactor and create flight class

from configparser import ConfigParser
from datetime import datetime, timedelta
from math import floor
from os import chdir, path
from statistics import mean

from flask import Flask, render_template, request, jsonify, make_response, g
from werkzeug.exceptions import InternalServerError

from dbhandler import DatabaseHandler

app = Flask(__name__)  # Create Flask application
db = DatabaseHandler()

# String templates
DATE_FORMAT = "%Y-%m-%d"
MONTH_FORMAT = "%Y-%m"
YEAR_FORMAT = "%Y"


def get_available_meters():
    meter_list = []
    db_result = db.select("SELECT * FROM zaehlpunkte")

    for result in db_result:
        meter_list.append({
            'id': result[0],  # result[0] --> zaehler_id
            'lastname': result[1],  # result[1] --> kunde_name
            'firstname': result[2],  # result[2] --> kunde_vorname
            'zipcode': result[3],  # result[3] --> plz
            'city': result[4]  # result[4] --> ort
        })

    for meter in meter_list:
        meter_min = db.select("SELECT MIN(datum_zeit) FROM zaehlwerte WHERE zaehler_id = ?", meter['id'])
        meter_max = db.select("SELECT MAX(datum_zeit) FROM zaehlwerte WHERE zaehler_id = ?", meter['id'])
        meter['min'] = meter_min
        meter['max'] = meter_max

    return meter_list


def add_month(date):
    """This function increments a given month by one month.

    :param date: The date which has to be increased by one month
    :type date: datetime
    :return: The incremented month
    :rtype: datetime
    """
    date_string = datetime.strftime(date, MONTH_FORMAT)
    str_list = date_string.split("-")

    if int(str_list[1]) == 12:
        next_month = str(1)
    else:
        next_month = str(int(str_list[1]) + 1)

    return_str = str_list[0] + "-" + next_month
    return datetime.strptime(return_str, MONTH_FORMAT)


def add_year(date):
    """This function increments a given year by one year.

    :param date: The date which has to be increased by one year
    :type date: datetime
    :return: The incremented year
    :rtype: datetime
    """
    date_string = datetime.strftime(date, YEAR_FORMAT)
    next_year = str(int(date_string) + 1)
    return_str = next_year
    return datetime.strptime(return_str, YEAR_FORMAT)


def parse_meter_values(result):
    """
        Calculate the load differences between two following dates or times and adds this to the return dictionary.
        The min, max and average load values are calculated and added as well.

        :param result: The result of a SQL query
        :type result: list
        :return: All entries from the SQL query result and some statistical data
        :rtype: dict
        """
    times = []
    meter_readings = []
    energy_diffs = []

    for res in result:
        times.append(res[0])  # res[0] --> datum_zeit
        meter_readings.append(float(res[1]))  # res[1] --> obis_180

    for i in range(len(times) - 1):
        energy_diffs.append((floor(meter_readings[i + 1] * 100) - floor(meter_readings[i] * 100)) / 100)

    # Remove last entries as times and meter_readings are larger than energy_diffs
    times.pop()
    meter_readings.pop()

    # Create list of meter data tuples
    meter_data_list = []
    for i, time in enumerate(times):
        meter_data_list.append({'datetime': time, 'reading': meter_readings[i], 'diff': energy_diffs[i]})

    response_dict = {
        'meter_data': meter_data_list,
        'min': min(energy_diffs),
        'max': max(energy_diffs),
        'avg': round(mean(energy_diffs), 3),
        'sum': round(sum(energy_diffs), 2)
    }

    return response_dict


def generate_day_query(meter_id, start, end, res):
    return "SELECT DATETIME(datum_zeit), obis_180 FROM zaehlwerte WHERE datum_zeit BETWEEN '{} 00:00:00' " \
           "AND '{}' AND STRFTIME('%M', datum_zeit) % {} = 0 AND zaehler_id = '{}' ORDER BY datum_zeit " \
           .format(start, end, res, meter_id)


@app.route('/')
def root():
    """
    This function returns the website which serves as the frontend for this application.

    :return: Website index.html
    :rtype: HTML file
    """

    stored_meters = get_available_meters()
    return render_template('selection.html', meters=stored_meters)


def get_meter_data(query):
    db_result = db.select(query)
    return parse_meter_values(db_result)


@app.route('/meters/<meter_id>/day/quarter')
def day_quarter_meter(meter_id):
    """
    response_dict = {
        'meter_data': meter_data_list,
        'min': min(energy_diffs),
        'max': max(energy_diffs),
        'avg': round(mean(energy_diffs), 3),
        'sum': round(sum(energy_diffs), 2)
    }
    """
    g.hour = True   # Set format for datetime display
    day = datetime.strptime(request.args['d'], "%Y-%m-%d")
    next_day = day + timedelta(days=1)
    query = generate_day_query(meter_id, day, next_day, 15)

    data = get_meter_data(query)
    return render_template("meter.html", title='Uhrzeit', unit='kWh/15 min', meters=data['meter_data'])


@app.route('/meters/<meter_id>/day/hour')
def day_hour_meter(meter_id):
    day = datetime.strptime(request.args['d'], "%Y-%m-%d")
    next_day = day + timedelta(days=1)
    query = generate_day_query(meter_id, day, next_day, 60)

    response = parse_meter_values(db.select(query))


@app.route('/meters/<meter_id>/interval')
def interval_meter(meter_id):
    start_day = datetime.strptime(request.args['sd'], DATE_FORMAT)
    end_day = datetime.strptime(request.args['ed'], DATE_FORMAT)
    next_day = end_day + timedelta(days=1)

    query = "SELECT DATE(datum_zeit), obis_180 FROM zaehlwerte WHERE DATE(datum_zeit) BETWEEN '{0}' AND '{1}' " \
            "AND zaehler_id = '{2}' AND TIME(datum_zeit) = '00:00:00' ORDER BY datum_zeit ASC" \
        .format(start_day.date(), next_day.date(), meter_id)

    response = parse_meter_values(db.select(query))


@app.route('/meters/<meter_id>/month')
def month_meter(meter_id):
    g.day = True    # Set format for datetime display
    month = datetime.strptime(request.args['m'], MONTH_FORMAT)
    next_month = add_month(month)

    query = "SELECT DATE(datum_zeit), obis_180 FROM zaehlwerte WHERE DATE(datum_zeit) BETWEEN '{0}' AND '{1}' " \
            "AND TIME(datum_zeit) = '00:00:00' AND zaehler_id = '{2}' ORDER BY datum_zeit ASC" \
        .format(month.strftime(DATE_FORMAT), next_month.strftime(DATE_FORMAT), meter_id)

    response = parse_meter_values(db.select(query))


@app.route('/meters/<meter_id>/year')
def year_meter(meter_id):
    g.month = True  # Set format for datetime display
    year = datetime.strptime(request.args['y'], YEAR_FORMAT)
    next_year = add_year(year)

    query = "SELECT DATE(datum_zeit, '%Y-%m-%d'), obis_180 FROM zaehlwerte WHERE STRFTIME('%Y', datum_zeit) " \
            "BETWEEN '{0}' AND '{1}' AND STRFTIME('%d', datum_zeit) = '01' AND TIME(datum_zeit) = '00:00:00' " \
            "AND zaehler_id = '{2}' ORDER BY datum_zeit ASC" \
        .format(year.strftime(YEAR_FORMAT), next_year.strftime(YEAR_FORMAT), meter_id)

    response = parse_meter_values(db.select(query))


def format_datetime(value, fmt='hour'):
    """Custom filter for datetimes"""
    dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    if fmt == 'hour':
        fmt = '%H:%M'
    elif fmt == 'day':
        fmt = '%D.%m'
    elif fmt == 'month':
        fmt = '%B %Y'
    return dt.strftime(fmt)


app.jinja_env.filters['datetime'] = format_datetime


# Run Flask server with the selected settings
if __name__ == '__main__':
    app.run(host='0.0.0.0', port='5000', debug=True)  # Visible in network
    # app.run(port='5000', debug=True)    # Not visible in network, only on localhost
