from m5stack import *
from m5ui import *
from uiflow import *
from machine import UART

setScreenColor(0x222222)

label_time = M5TextBox(5, 5, "Heure: --", lcd.FONT_Default, 0xFFFFFF, rotate=0)
label_fix = M5TextBox(5, 30, "Fix: --", lcd.FONT_Default, 0xFFFFFF, rotate=0)
label_sat = M5TextBox(5, 55, "Satellites: --", lcd.FONT_Default, 0xFFFFFF, rotate=0)
label_lat = M5TextBox(5, 80, "Latitude: --", lcd.FONT_Default, 0xFFFFFF, rotate=0)
label_lon = M5TextBox(5, 105, "Longitude: --", lcd.FONT_Default, 0xFFFFFF, rotate=0)
label_alt = M5TextBox(5, 130, "Altitude: --", lcd.FONT_Default, 0xFFFFFF, rotate=0)

uart = UART(1, tx=17, rx=16)
uart.init(115200, bits=8, parity=None, stop=1)

buffer = ""

def nmea_to_decimal(coord, direction):
    # coord format brut NMEA: "3442.26795" = 34 degres + 42.26795 minutes
    degres_len = 2 if direction in ('N', 'S') else 3
    degres = int(coord[0:degres_len])
    minutes = float(coord[degres_len:])
    decimal = degres + minutes / 60
    if direction in ('S', 'W'):
        decimal = -decimal
    return decimal

while True:
    if uart.any():
        data = uart.read()
        buffer += data.decode('utf-8', 'ignore')

        if '\n' in buffer:
            lines = buffer.split('\n')
            buffer = lines[-1]

            gga_lines = [l for l in lines if 'GGA' in l]

            if gga_lines:
                trame = gga_lines[-1].strip()
                champs = trame.split(',')

                # $GNGGA,heure,lat,N/S,lon,E/W,qualite,nb_sat,hdop,alt,M,...
                if len(champs) >= 10:
                    heure_brute = champs[1]
                    lat_brute = champs[2]
                    lat_dir = champs[3]
                    lon_brute = champs[4]
                    lon_dir = champs[5]
                    qualite = champs[6]
                    nb_satellites = champs[7]
                    altitude = champs[9]

                    label_time.setText('Heure: ' + heure_brute[0:6] + ' UTC')
                    label_fix.setText('Fix: ' + ('OK' if qualite != '0' else 'aucun'))
                    label_sat.setText('Satellites: ' + nb_satellites)

                    if lat_brute and lon_brute:
                        lat_decimal = nmea_to_decimal(lat_brute, lat_dir)
                        lon_decimal = nmea_to_decimal(lon_brute, lon_dir)
                        label_lat.setText('Latitude: ' + str(round(lat_decimal, 5)))
                        label_lon.setText('Longitude: ' + str(round(lon_decimal, 5)))
                    else:
                        label_lat.setText('Latitude: --')
                        label_lon.setText('Longitude: --')

                    label_alt.setText('Altitude: ' + altitude + ' m')

    wait_ms(300)