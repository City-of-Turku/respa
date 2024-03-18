# Qualitytool Django management commands


## Qualitytool command: post_daily_utilization

### Overview
This command posts the daily utilization of respa resources to Suomi.fi qualitytool API

### Usage
To use the command, run:

```
python manage.py post_daily_utilization [Optional: --date YYYY-mm-dd]
```

### Options
- `--date YYYY-mm-dd (Optional)`: The date for which the utilization data should be uploaded. Defaults to the current date (`datetime.now().date()`).

### Example
To upload utilization data for January 1, 2023:

```
python manage.py post_daily_utilization --date 2023-01-01
```


## Qualitytool command: save_daily_utilization_csv

### Overview
This command saves the daily utilization of respa resources to a given file path.

### Usage
To use the command, run:

```
python manage.py save_daily_utilization_csv /file/path.csv [Optional: --date YYYY-mm-dd]
```

### Options
- `path`: The destination filepath
- `--date YYYY-mm-dd (Optional)`: The date for which the utilization data should be uploaded. Defaults to the current date (`datetime.now().date()`).

### Example
To upload utilization data for January 1, 2023:

```
python manage.py save_daily_utilization_csv /file/path.csv --date 2023-01-01
```

## Qualitytool command: sftp_daily_utilization

### Overview
This command uploads the daily utilization of respa resources to a sftp server.

### Usage
To use the command, run:

```
python manage.py sftp_daily_utilization /file/path.csv [Optional: --date YYYY-mm-dd]
```

### Environment Variables
Ensure the following environment variables are set before running the command:

- `QUALITYTOOL_SFTP_HOST`: The hostname of the SFTP server.
- `QUALITYTOOL_SFTP_PORT`: The port number for SFTP (e.g., 22).
- `QUALITYTOOL_SFTP_USERNAME`: The username for authenticating with the SFTP server.
- `QUALITYTOOL_SFTP_PASSWORD`: The password for authenticating with the SFTP server.

### Options
- `path`: The destination filepath on the SFTP server where the utilization CSV file will be uploaded.
- `--date YYYY-mm-dd (Optional)`: The date for which the utilization data should be uploaded. Defaults to the current date (`datetime.now().date()`).

### Example
To upload utilization data for January 1, 2023:

```
python manage.py sftp_daily_utilization /file/path.csv --date 2023-01-01
```
