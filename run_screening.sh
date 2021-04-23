#!/bin/bash

counter=1
while [ $counter -le 105 ]
do
        echo $counter
        ((counter++))
        fab run-screening-one
        sleep 1
done

echo All done