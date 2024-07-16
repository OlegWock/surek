import { loadConfig } from '@src/config';
import { version } from '../package.json' assert { type: "json" };
import { command, subcommands } from 'cmd-ts';
import Docker from 'dockerode';
import { log } from '@src/logger';
import { SUREK_NETWORK, SYSTEM_SERVICES_CONFIG, DEFAULT_SUREK_LABELS } from '@src/const';
import { deployStack, stopStack } from '@src/stacks';

const start = command({
    name: 'start',
    description: 'Ensure correct Docker configuration and run system containers',
    args: {},
    handler: async () => {
        const config = loadConfig();
        log.info('Loaded config');
        const docker = new Docker();

        const networks = await docker.listNetworks();
        const surekNetwork = networks.find(n => n.Name === SUREK_NETWORK);
        if (!surekNetwork) {
            log.info('Surek network is missing, creating');
            await docker.createNetwork({
                Name: SUREK_NETWORK,
                Labels: {
                    ...DEFAULT_SUREK_LABELS,
                }
            });
        }

        await stopStack(SYSTEM_SERVICES_CONFIG);
        await deployStack(SYSTEM_SERVICES_CONFIG, config);
    },
});

const stop = command({
    name: 'stop',
    description: `Stops Surek system containers (doesn't stop user containers)`,
    args: {},
    handler: async () => {
        await stopStack(SYSTEM_SERVICES_CONFIG);
    },
});

export const app = subcommands({
    name: 'surek',
    version,
    cmds: { start, stop },
})

