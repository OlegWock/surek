import { loadConfig } from '@src/config';
import { version } from '../package.json' assert { type: "json" };
import { command, subcommands, string, positional } from 'cmd-ts';
import Docker from 'dockerode';

import { log } from '@src/logger';
import { SUREK_NETWORK, SYSTEM_SERVICES_CONFIG, DEFAULT_SUREK_LABELS } from '@src/const';
import { deployStack, deployStackByConfigPath, getAvailableStacks, stopStack, stopStackByConfigPath } from '@src/stacks';
import { exit } from '@src/utils';
import { dirname } from 'path';

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

        await stopStackByConfigPath(SYSTEM_SERVICES_CONFIG);
        await deployStackByConfigPath(SYSTEM_SERVICES_CONFIG, config);
    },
});

const systemStop = command({
    name: 'stop',
    description: `Stops Surek system containers`,
    args: {},
    handler: async () => {
        await stopStackByConfigPath(SYSTEM_SERVICES_CONFIG);
    },
});

const ls = command({
    name: 'ls',
    description: `Output list of available stacks`,
    args: {},
    handler: async () => {
        const stacks = getAvailableStacks();
        const names = Object.keys(stacks);
        if (names.length === 0) {
            log.info('No stacks available');
        } else {
            log.info('Available stacks:');
            Object.entries(stacks).map(([name, stack]) => {
                log.info(name, '->', stack.path);
            });
        }
    },
});

const deploy = command({
    name: 'deploy',
    description: `Deploy stack`,
    args: {
        stackName: positional({ type: string, displayName: 'stack name' }),
    },
    handler: async ({ stackName }) => {
        const config = loadConfig();
        const stacks = getAvailableStacks();
        const stack = stacks[stackName];
        if (!stack) {
            return exit(`Unknown stack ${stackName}`);
        }
        log.info('Loaded stack config from', stack.path);

        deployStack(stack.config, dirname(stack.path), config);
    },
});

const stop = command({
    name: 'stop',
    description: `Stop deployed stack`,
    args: {
        stackName: positional({ type: string, displayName: 'stack name' }),
    },
    handler: async ({ stackName }) => {
        const stacks = getAvailableStacks();
        const stack = stacks[stackName];
        if (!stack) {
            return exit(`Unknown stack ${stackName}`);
        }
        log.info('Loaded stack config from', stack.path);

        stopStack(stack.config, dirname(stack.path), false);
    },
});

const system = subcommands({
    name: 'system',
    description: 'Control Surek system containers',
    cmds: { start, stop: systemStop }
})

export const app = subcommands({
    name: 'surek',
    version,
    cmds: { system, ls, deploy, stop },
})

