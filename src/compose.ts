import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import yaml from 'js-yaml';
import { ComposeSpecification, ListOrDict } from './compose-spec.js';
import { exapndVariables, StackConfig, SurekConfig } from './config.js';
import { getDataDir, DEFAULT_SUREK_LABELS, IS_DEV, SUREK_NETWORK } from './const.js';
import { exit } from './utils/misc.js';
import { log } from './utils/logger.js';
import { join } from 'node:path';
import { hashSync } from 'bcrypt';
import { getStackProjectDir } from './stacks.js';

export const readComposeFile = (path: string) => {
    const text = readFileSync(path, { encoding: 'utf-8' });
    const parsed = yaml.load(text);
    return parsed as ComposeSpecification;
};

export const transformSystemComposeFile = (originalSpec: ComposeSpecification, config: SurekConfig): ComposeSpecification => {
    if (!config.backup && originalSpec.services) {
        delete originalSpec.services['backup'];
    }
    return originalSpec;
};

export const transformComposeFile = (originalSpec: ComposeSpecification, config: StackConfig, surekConfig: SurekConfig): ComposeSpecification => {
    const spec = structuredClone(originalSpec);

    const dataDir = getDataDir();
    const volumesDir = join(dataDir, 'volumes', config.name);
    const foldersToCreate: string[] = [];

    if (!spec.networks) {
        spec.networks = {}
    }
    spec.networks[SUREK_NETWORK] = {
        name: SUREK_NETWORK,
        external: true,
    };

    if (spec.volumes) {
        Object.keys(spec.volumes).forEach((name) => {
            if (config.backup.excludeVolumes.includes(name)) {
                return;
            }

            const descriptor = spec.volumes![name] ?? {};
            const preConfigured = Object.keys(descriptor).length;
            if (preConfigured) {
                log.warn(`Volume ${name} is already pre-configured. This volume will be skipped on backup.`);
                return;
            }
            const folderPath = join(volumesDir, name);
            foldersToCreate.push(folderPath);
            spec.volumes![name] = {
                driver: 'local',
                driver_opts: {
                    type: 'none',
                    o: 'bind',
                    device: folderPath,
                },
                labels: {
                    ...DEFAULT_SUREK_LABELS,
                }
            };
        });
    }

    config.public.map(({ domain, target, auth }) => {
        const [service, port = 80] = target.split(':');
        if (!spec.services?.[service]) {
            return exit(`Service ${service} not defined in docker-compose config`);
        }
        if (!spec.services[service].labels) {
            spec.services[service].labels = {};
        }

        const labelsToAdd: Record<string, string> = {
            ...DEFAULT_SUREK_LABELS,
            'caddy': exapndVariables(domain, surekConfig),
            'caddy.reverse_proxy': `{{upstreams ${port}}}`,
        }
        if (IS_DEV) {
            labelsToAdd['caddy.tls'] = "internal";
        }

        if (auth) {
            const [user, password] = exapndVariables(auth, surekConfig).split(':');
            const hashedPassword = hashSync(password, 14);
            labelsToAdd[`caddy.basic_auth`] = '';
            // Replace $ with $$. Ref: https://caddy.community/t/using-caddyfiles-basic-auth-with-environment-variables-and-docker/19918/2
            labelsToAdd[`caddy.basic_auth.${user}`] = hashedPassword.replaceAll('$', '$$$$');
        }

        if (Array.isArray(spec.services[service].labels)) {
            spec.services[service].labels.push(...Object.entries(labelsToAdd).map(([key, val]) => `${key}=${JSON.stringify(val)}`));
        } else {
            Object.assign(spec.services[service].labels, labelsToAdd);
        }
    });

    if (config.env && spec.services) {
        Object.entries(spec.services).forEach(([service, desc]) => {
            const containerSpecificEnv = (config.env?.byContainer?.[service] ?? []).map(env => exapndVariables(env, surekConfig));
            const sharedEnv = (config.env?.shared ?? []).map(env => exapndVariables(env, surekConfig));
            desc.environment = mergeEnvs(desc.environment ?? [], sharedEnv, containerSpecificEnv);
        });
    }

    // TODO: probably shouldn't do side effects in this function
    foldersToCreate.forEach(path => mkdirSync(path, { recursive: true }));

    if (spec.services) {
        Object.entries(spec.services).forEach(([key, service]) => {
            if (service.network_mode) {
                return;
            }
            if (!service.networks) {
                service.networks = [];
            }
            if (Array.isArray(service.networks)) {
                service.networks.push(SUREK_NETWORK);
            } else {
                service.networks[SUREK_NETWORK] = null;
            }
        })
    }

    // * Rewrite named volumes to local binds into Surek-managed folder https://stackoverflow.com/a/49920624/4712003

    return spec;
};

export const writeComposeFile = (path: string, content: ComposeSpecification) => {
    const text = yaml.dump(content);
    writeFileSync(path, text);
};

export const getPathForPatchedComposeFile = (config: StackConfig) => {
    const projectDir = getStackProjectDir(config.name);
    const patchedFilePath = join(projectDir, 'docker-compose.surek.yml');
    return patchedFilePath;
};

type ExecDockerComposeOptions = {
    composeFile: string
    projectFolder?: string,
    command: 'up' | 'stop' | 'ps',
    options?: (string | string[])[],
    args?: string[],
    silent?: boolean,
};

export const execDockerCompose = ({ composeFile, projectFolder, command, options, args, silent }: ExecDockerComposeOptions) => {
    const commandArgs: string[] = ['compose'];

    commandArgs.push('--file', composeFile);
    if (projectFolder) {
        commandArgs.push('--project-directory', projectFolder);
    }

    commandArgs.push(command);
    if (options) {
        commandArgs.push(...options.flat());
    }
    if (args) {
        commandArgs.push(...args);
    }

    if (!silent) {
        log.info('Executing docker command');
        log.info(`$ docker ${commandArgs.join(' ')}`);
    }
    let stdout = '';
    const childProcess = spawn('docker', commandArgs);
    childProcess.stdout.on('data', (data) => {
        const chunk = data.toString();
        stdout += chunk;
        if (!silent) process.stdout.write(chunk);
    });
    childProcess.stderr.on('data', (data) => {
        if (!silent) process.stderr.write(data.toString());
    });
    return new Promise<string>((resolve, reject) => {
        childProcess.on('error', (error) => {
            reject(error);
        });
        childProcess.on('exit', (code) => {
            if (code === 0) {
                resolve(stdout);
            } else {
                reject(new Error(`Command exited with code ${code}.`));
            }
        });
    });
};

const mergeEnvs = (original: ListOrDict, ...extensions: string[][]) => {
    if (Array.isArray(original)) {
        return [...original, ...extensions.flat()];
    } else {
        return {
            ...original,
            ...Object.fromEntries(extensions.flat().map(e => e.split('='))),
        };
    }
};