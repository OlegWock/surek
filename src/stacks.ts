import fg from 'fast-glob';
import { execDockerCompose, getPathForPatchedComposeFile, readComposeFile, transformComposeFile, transformSystemComposeFile, writeComposeFile } from "./compose.js";
import { loadStackConfig, StackConfig, SurekConfig } from "./config.js";
import { getDataDir, SYSTEM_DIR } from "./const.js";
import { log } from "./utils/logger.js";
import { exit } from "./utils/misc.js";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { pullGithubRepo } from './github.js';
import { copyFolderRecursivelyWithOverwrite } from './utils/fs.js';
import { fromError } from 'zod-validation-error';

export const getStackProjectDir = (name: string) => join(getDataDir(), "projects", name);

export const startStack = async (config: StackConfig) => {
    const patchedFilePath = getPathForPatchedComposeFile(config);
    const projectDir = getStackProjectDir(config.name);
    log.info(`Starting containers...`)
    await execDockerCompose({
        composeFile: patchedFilePath,
        projectFolder: projectDir,
        command: 'up',
        options: ['-d', '--build']
    });
    log.info(`Containers started`);
};

export const deployStackByConfigPath = (configPath: string, surekConfig: SurekConfig) => {
    log.info(`Loading Surek stack config ${configPath}`);
    const config = loadStackConfig(configPath);
    return deployStack(config, dirname(configPath), surekConfig);
};

export const deployStack = async (config: StackConfig, sourceDir: string, surekConfig: SurekConfig) => {
    const projectDir = getStackProjectDir(config.name);
    if (existsSync(projectDir)) {
        rmSync(projectDir, { recursive: true });
    }
    mkdirSync(projectDir, { recursive: true });

    if (config.source.type === 'github') {
        // TODO: probably need to cache commit hash after pull and skip if it matches or something?
        // Currently re-downloading repo triggers Docker image to be built again, even if repo content didn't change
        await pullGithubRepo(config, projectDir, surekConfig);
    }

    copyFolderRecursivelyWithOverwrite(sourceDir, projectDir);

    const composeFilePath = resolve(projectDir, config.composeFilePath);
    if (!existsSync(composeFilePath)) {
        return exit(`Couldn't find compose file at ${composeFilePath}`);
    }
    let composeFile = readComposeFile(composeFilePath);
    if (config.name === 'surek-system' && sourceDir === SYSTEM_DIR) {
        composeFile = transformSystemComposeFile(composeFile, surekConfig);
    }
    const transformed = transformComposeFile(composeFile, config, surekConfig);
    const patchedFilePath = getPathForPatchedComposeFile(config);
    writeComposeFile(patchedFilePath, transformed);
    log.info(`Saved patched compose file at ${patchedFilePath}`);
    startStack(config)
};

export const stopStackByConfigPath = (configPath: string, silent = false) => {
    const config = loadStackConfig(configPath);
    return stopStack(config, dirname(configPath), silent);
};

export const stopStack = async (config: StackConfig, sourceDir: string, silent = false) => {
    const patchedComposeFile = getPathForPatchedComposeFile(config);
    if (!existsSync(patchedComposeFile)) {
        if (silent) return;
        return exit(`Couldn't find compose file for this stack`);
    }

    await execDockerCompose({
        composeFile: patchedComposeFile,
        projectFolder: sourceDir,
        command: 'stop',
    });
    log.info(`Containers stopped`);
};

type StackInfo = { name: string, config: StackConfig, path: string, valid: true, error: '' };
type InvalidStackInfo = { name: '', config: null, path: string, valid: false, error: string };

export const getAvailableStacks = (): (StackInfo | InvalidStackInfo)[] => {
    const stacksDir = join(process.cwd(), 'stacks');
    if (!existsSync(stacksDir)) {
        return exit(`Folder 'stacks' not found in current working directory`);
    }
    const stacks = fg.sync('**/surek.stack.yml', { cwd: stacksDir });
    const stacksInfo = stacks.map(path => {
        const configPath = join(stacksDir, path);
        try {
            const config = loadStackConfig(configPath);
            return { name: config.name, config, path: configPath, valid: true, error: '' } as StackInfo;
        } catch (err) {
            const validationError = fromError(err);
            return { name: '', config: null, path: configPath, valid: false, error: validationError.toString() } as InvalidStackInfo;
        }
    }).sort((a, b) => a.path.localeCompare(b.path));

    return stacksInfo;
};

export const getStackByName = (name: string) => {
    if (!name) {
        return exit('Invalid stack name');
    }
    const stacks = getAvailableStacks();
    const stack = stacks.find(s => s.name === name);
    if (!stack) {
        return exit(`Stack with name '${name}' not found`);
    }
    return stack as StackInfo;
};

export const getStackStatus = async (name: string) => {
    const dir = getStackProjectDir(name);
    const composeFile = join(dir, 'docker-compose.surek.yml');
    if (!existsSync(dir) || !existsSync(composeFile)) {
        return '× Not deployed';
    }

    const output = await execDockerCompose({
        composeFile,
        silent: true,
        projectFolder: dir,
        command: 'ps',
        args: ['--format', 'json'],
    });

    const services = output.split('\n').flatMap(s => {
        try {
            return [JSON.parse(s)];
        } catch (err) {
            return [];
        }
    });

    const runningContainers = services.filter(s => s.State === 'running');
    if (runningContainers.length === 0) {
        return '× Down';
    } else if (runningContainers.length === services.length) {
        return `✓ Running`
    } else {
        return `✓ Running (${runningContainers.length}/${services.length})`;
    }
};