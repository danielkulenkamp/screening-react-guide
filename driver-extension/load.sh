#!/bin/bash

if [ "${UID}" -ne 0  ]
then
    echo "Must be root to run this script"
    exit 1
fi

rmmod ath9k
rmmod ath9k_common
rmmod ath9k_hw
rmmod ath
rmmod mac80211
rmmod cfg80211
rmmod compat

# Exit on error after this point
set -e

insmod athmodules/compat.ko
insmod athmodules/cfg80211.ko
insmod athmodules/mac80211.ko
insmod athmodules/ath.ko
insmod athmodules/ath9k_hw.ko
insmod athmodules/ath9k_common.ko
insmod athmodules/ath9k.ko
