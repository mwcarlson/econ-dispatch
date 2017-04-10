# -*- coding: utf-8 -*- {{{
# vim: set fenc=utf-8 ft=python sw=4 ts=4 sts=4 et:

# Copyright (c) 2017, Battelle Memorial Institute
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation
# are those of the authors and should not be interpreted as representing
# official policies, either expressed or implied, of the FreeBSD
# Project.
#
# This material was prepared as an account of work sponsored by an
# agency of the United States Government.  Neither the United States
# Government nor the United States Department of Energy, nor Battelle,
# nor any of their employees, nor any jurisdiction or organization that
# has cooperated in the development of these materials, makes any
# warranty, express or implied, or assumes any legal liability or
# responsibility for the accuracy, completeness, or usefulness or any
# information, apparatus, product, software, or process disclosed, or
# represents that its use would not infringe privately owned rights.
#
# Reference herein to any specific commercial product, process, or
# service by trade name, trademark, manufacturer, or otherwise does not
# necessarily constitute or imply its endorsement, recommendation, or
# favoring by the United States Government or any agency thereof, or
# Battelle Memorial Institute. The views and opinions of authors
# expressed herein do not necessarily state or reflect those of the
# United States Government or any agency thereof.
#
# PACIFIC NORTHWEST NATIONAL LABORATORY
# operated by BATTELLE for the UNITED STATES DEPARTMENT OF ENERGY
# under Contract DE-AC05-76RL01830
# }}}

import json
import os
import numpy as np

from econ_dispatch.component_models import ComponentBase
from econ_dispatch.utils import least_squares_regression


def fahrenheit_to_kelvin(t):
    return (t - 32) / 1.8 + 273.15


DEFAULT_TCHO = 45.8
DEFAULT_TCDI = 83.7
DEFAULT_TGENI = 335
DEFAULT_QIN = 8.68


class Component(ComponentBase):
    def __init__(self, **kwargs):
        super(Component, self).__init__(**kwargs)
        #Chilled water temperature setpoint outlet from absorption chiller
        self.Tcho = DEFAULT_TCHO

        # Condenser water temperature inlet temperature to absorption chiller from heat rejection in F
        self.Tcdi = DEFAULT_TCDI

        # Generator inlet temperature (hot water temperature inlet to abs chiller) in F
        self.Tgeni = DEFAULT_TGENI

        # heat input to the generator in mmBTU/hr
        self.Qin = DEFAULT_QIN

        # Gordon-Ng model coefficients
        self.a0, self.a1 = self.train()

    def get_output_metadata(self):
        return [u"chilled_water"]

    def get_input_metadata(self):
        return [u"heat"]

    def get_optimization_parameters(self):
        Qch = self.predict()
        return {"Qch":Qch}

    def update_parameters(self,
                          Tcho=DEFAULT_TCHO,
                          Tcdi=DEFAULT_TCDI,
                          Tgeni=DEFAULT_TGENI,
                          Qin=DEFAULT_QIN):
        self.Tcho = Tcho
        self.Tcdi = Tcdi
        self.Tgeni = Tgeni
        self.Qin = Qin

    def predict(self):
        # Regression models were built separately (Training Module) and
        # therefore regression coefficients are available. Heat input to the chiller generator
        # is assumed to be known and this model predicts the chiller cooling output.
        # This code is meant to be used for 4 hours ahead predictions.
        # The code creates an excel file and writes
        # the results on it along with time stamps.

        Tcho = fahrenheit_to_kelvin(self.Tcho)
        Tcdi = fahrenheit_to_kelvin(self.Tcdi)
        Tgeni = fahrenheit_to_kelvin(self.Tgeni)
        Qin = 293.1 * self.Qin #Converting mmBTU/hr to kW

        Qch = (Qin * ((Tgeni - Tcdi) / Tgeni) - self.a0 - self.a1 * (Tcdi / Tgeni)) / ((Tgeni - Tcho) / Tcho)
        Qch = Qch / 3.517 #Converting kW to cooling ton
        return Qch

    def train(self):
        # This module reads the historical data on temperatures (in Fahrenheit), inlet heat to the
        # chiller (in mmBTU/hr) and outlet cooling load (in cooling ton) then, converts
        # the data to proper units which then will be used for model training. At
        # the end, regression coefficients will be written to a file

        data_file = os.path.join(os.path.dirname(__file__), 'CH-Abs-Historical-Data.json')
        with open(data_file, 'r') as f:
            historical_data = json.load(f)

        Tcho = historical_data["Tcho(F)"]# chilled water supply temperature in F
        Tcdi = historical_data["Tcdi(F)"]# inlet temperature from condenser in F
        Tgeni = historical_data["Tgei(F)"]# generator inlet water temperature in F
        Qch = historical_data["Qch(tons)"]# chiller cooling output in cooling Tons
        Qin = historical_data["Qin(MMBtu/h)"]# chiller heat input in mmBTU/hr
        i = len(Tcho)

        # *********************************

        COP = np.zeros(i) # Chiller COP
        x1 = np.zeros(i)
        y = np.zeros(i)

        for a in range(i):
            Tcho[a] = fahrenheit_to_kelvin(Tcho[a])
            Tcdi[a] = fahrenheit_to_kelvin(Tcdi[a])
            Tgeni[a] = fahrenheit_to_kelvin(Tgeni[a])
            Qch[a] = 3.517 * Qch[a]#Converting cooling tons to kW
            Qin[a] = 293.1 * Qin[a]#Converting mmBTU/hr to kW
            COP[a] = float(Qch[a]) / float(Qin[a])

        for a in range(i):
            x1[a] = float(Tcdi[a]) / float(Tgeni[a])
            y[a] = ((Tgeni[a] - Tcdi[a]) / float((Tgeni[a] * COP[a])) - ((Tgeni[a] - Tcho[a]) / float(Tcho[a]))) * Qch[a]

        AA = least_squares_regression(inputs=x1, output=y)

        return AA
