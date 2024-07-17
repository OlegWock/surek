import { spawnSync, spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import yaml from 'js-yaml';
import { ComposeSpecification, ListOrDict } from '@src/compose-spec';
import { exapndVariables, loadStackConfig, StackConfig, SurekConfig } from '@src/config';
import { DATA_DIR, DEFAULT_SUREK_LABELS, IS_DEV, SUREK_NETWORK } from '@src/const';
import { exit } from '@src/utils';
import { log } from '@src/logger';
import { join } from 'node:path';
import { hashSync } from 'bcrypt';

export const readComposeFile = (path: string) => {
    const text = readFileSync(path, { encoding: 'utf-8' });
    const parsed = yaml.load(text);
    return parsed as ComposeSpecification;
};

export const transformComposeFile = (originalSpec: ComposeSpecification, config: StackConfig, surekConfig: SurekConfig): ComposeSpecification => {
    const spec = structuredClone(originalSpec);

    const projectDir = join(DATA_DIR, "projects", config.name, 'volumes');
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
            const folderPath = join(projectDir, name);
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
    const projectDir = join(DATA_DIR, "projects", config.name);
    const patchedFilePath = join(projectDir, 'docker-compose.yml');
    return patchedFilePath;
};

type ExecDockerComposeOptions = {
    composeFile: string
    projectFolder?: string,
    command: 'up' | 'stop',
    options?: (string | string[])[],
    args?: string[],
};

export const execDockerCompose = ({ composeFile, projectFolder, command, options, args }: ExecDockerComposeOptions) => {
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

    log.info('Executing docker command');
    log.info(`$ docker ${commandArgs.join(' ')}`);
    const childProcess = spawn('docker', commandArgs);
    childProcess.stdout.on('data', (data) => {
        process.stdout.write(data.toString());
    });
    childProcess.stderr.on('data', (data) => {
        process.stderr.write(data.toString());
    });
    return new Promise<void>((resolve, reject) => {
        childProcess.on('error', (error) => {
            reject(error);
        });
        childProcess.on('exit', (code) => {
            if (code === 0) {
                resolve();
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