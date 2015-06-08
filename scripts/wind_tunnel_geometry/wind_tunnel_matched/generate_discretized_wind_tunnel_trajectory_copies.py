from __future__ import division

SCRIPT_ID = 'generate_discretized_wind_tunnel_trajectory_copies_and_geom_configs'
SCRIPT_NOTES = 'Run for all experiments and odor states.'

import os
import imp
import numpy as np

from db_api.connect import session
from db_api import models, add_script_execution

from plume import CollimatedPlume
from insect import Insect
from trial import TrialFromPositionSequence

# get configuration
from config.generate_discretized_wind_tunnel_trajectory_copies import *

# get wind tunnel connection and models
wt_session = imp.load_source('db_api.connect', os.path.join(WT_REPO, 'db_api', 'connect.py')).session
wt_models = imp.load_source('db_api.models', os.path.join(WT_REPO, 'db_api', 'models.py'))


def main(traj_limit=None):
    # add script execution to database
    add_script_execution(script_id=SCRIPT_ID, session=session, multi_use=False, notes=SCRIPT_NOTES)
    session.commit()

    for experiment_id in EXPERIMENT_IDS:

        for odor_state in ODOR_STATES:

            # make geom_config_group
            geom_config_group_id = '{}_{}_odor_{}'.format(GEOM_CONFIG_GROUP_ID, experiment_id, odor_state)
            geom_config_group = session.query(models.GeomConfigGroup).get(geom_config_group_id)

            # make simulation
            sim_id = SIMULATION_ID.format(experiment_id, odor_state)
            sim_description = SIMULATION_DESCRIPTION.format(experiment_id, odor_state)
            sim = models.Simulation(id=sim_id, description=sim_description)
            sim.env, sim.dt = ENV, DT
            sim.heading_smoothing = 0
            sim.geom_config_group = geom_config_group

            # make plume
            pl = CollimatedPlume(env=ENV, dt=DT)
            pl.set_params(**PLUME_PARAMS_DICT[experiment_id])
            if odor_state in ('none', 'afterodor'):
                pl.max_conc = 0
            pl.initialize()
            pl.generate_orm(models, sim=sim)

            # make insect
            ins = Insect(env=ENV, dt=DT)
            ins.set_params(**INSECT_PARAMS_DICT[experiment_id])
            ins.loglike_function = LOGLIKE
            ins.initialize()
            ins.generate_orm(models, sim=sim)

            # add simulation
            session.add(sim)
            session.commit()

            for gctr, geom_config in enumerate(geom_config_group.geom_configs):

                traj_id = geom_config.geom_config_extension_real_trajectory.real_trajectory_id
                traj = wt_session.query(wt_models.Trajectory).get(traj_id)

                # get positions from traj
                positions = traj.get_positions(wt_session)

                # create discretized version of trajectory
                trial = TrialFromPositionSequence(positions, pl, ins)

                # add timepoints to trial and generate data model
                trial.add_timepoints(models, session=session, heading_smoothing=sim.heading_smoothing)
                trial.generate_orm(models)

                # bind simulation, geom_config
                trial.orm.sim = sim
                trial.orm.geom_config = geom_config

                # add trial
                session.add(trial.orm)

                if traj_limit and gctr == traj_limit:
                    break

            # update total number of trials
            sim.total_trials = gctr
            session.add(sim)
            session.commit()

if __name__ == '__main__':
    main()