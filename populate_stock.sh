#!/bin/bash

terms=( "yahoo" "yhoo" "carol+bartz" )

while true
do
 for term in ${terms[@]} 
 do
 wget http://localhost:8080/populate/$term -q -O /dev/null
 sleep 60
 done
done 

