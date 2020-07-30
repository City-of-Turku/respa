#!/bin/bash


source env/bin/activate

while true
    do
        python3 manage.py handle_reminders
        sleep 300
    done