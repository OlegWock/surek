import { loadConfig, loadStackConfig } from './config.js';
import { command, subcommands, string, positional } from 'cmd-ts';
import Docker from 'dockerode';
import { log } from './utils/logger.js';
import { SUREK_NETWORK, SYSTEM_SERVICES_CONFIG, DEFAULT_SUREK_LABELS } from './const.js';
import { deployStack, deployStackByConfigPath, getAvailableStacks, getStackByName, getStackStatus, startStack, stopStack, stopStackByConfigPath } from './stacks.js';
import { dirname } from 'path';
import { fromError } from 'zod-validation-error';
import { Table } from 'console-table-printer';
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const packageJson = require("../package.json");


const systemStart = command({
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

        await stopStackByConfigPath(SYSTEM_SERVICES_CONFIG, true);
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

const deploy = command({
    name: 'deploy',
    description: `Deploy stack`,
    args: {
        stackName: positional({ type: string, displayName: 'stack name' }),
    },
    handler: async ({ stackName }) => {
        const config = loadConfig();
        const stack = getStackByName(stackName);
        log.info('Loaded stack config from', stack.path);

        deployStack(stack.config, dirname(stack.path), config);
    },
});

const start = command({
    name: 'start',
    description: `Start already transformed stack`,
    args: {
        stackName: positional({ type: string, displayName: 'stack name' }),
    },
    handler: async ({ stackName }) => {
        const stack = getStackByName(stackName);
        log.info('Loaded stack config from', stack.path);
        startStack(stack.config);
    },
});

const stop = command({
    name: 'stop',
    description: `Stop deployed stack`,
    args: {
        stackName: positional({ type: string, displayName: 'stack name' }),
    },
    handler: async ({ stackName }) => {
        const stack = getStackByName(stackName);
        log.info('Loaded stack config from', stack.path);

        stopStack(stack.config, dirname(stack.path), false);
    },
});

const validate = command({
    name: 'validate',
    description: `Validate stack config`,
    args: {
        stackPath: positional({ type: string, displayName: 'stack config path' }),
    },
    handler: async ({ stackPath }) => {
        try {
            const config = loadStackConfig(stackPath);
            log.info('Loaded stack config with name', config.name, 'from', stackPath);
            log.success('Config is valid');
        } catch (err) {
            const validationError = fromError(err);
            log.error('Error while loading config', stackPath);
            log.error(validationError.toString());
        }
    },
});

const status = command({
    name: 'status',
    description: 'Output status of Surek system containers and user stacks',
    args: {},
    handler: async () => {
        const config = loadConfig();
        const stacks = getAvailableStacks();
        log.info('Loaded available stacks');

        const systemStatus = await getStackStatus('surek-system');

        const stackRecords = await Promise.all(stacks.map(async (stack) => {
            if (!stack.valid) {
                return {
                    'Stack': stack.name,
                    'Status': 'Invalid config',
                    'Path': stack.path,
                }
            }
            return {
                'Stack': stack.name,
                'Status': await getStackStatus(stack.name),
                'Path': stack.path,
            }
        }));

        const table = new Table({
            columns: [
                {title: 'Stack', alignment: 'left', name: 'Stack'},
                {title: 'Status', alignment: 'left', name: 'Status'},
                {title: 'Path', alignment: 'left', name: 'Path'},
            ]
        });
        table.addRows([
            {
                'Stack': 'System containers',
                'Status': systemStatus,
                'Path': '',
            },
            ...stackRecords,
        ]);

        table.printTable();
    },
});

const system = subcommands({
    name: 'system',
    description: 'Control Surek system containers',
    cmds: { start: systemStart, stop: systemStop }
})

// TODO: better handle docker command errors (at least show to user!). E.g. when missing root permissions
export const app = subcommands({
    name: 'surek',
    version: packageJson.version,
    cmds: { status, system, start, deploy, stop, validate, },
})

