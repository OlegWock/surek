import fg from 'fast-glob';
import { execDockerCompose, getPathForPatchedComposeFile, readComposeFile, transformComposeFile, writeComposeFile } from "@src/compose";
import { loadStackConfig, StackConfig, SurekConfig } from "@src/config";
import { DATA_DIR, STACKS_DIR } from "@src/const";
import { log } from "@src/utils/logger";
import { exit } from "@src/utils/misc";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { pullGithubRepo } from '@src/github';
import { copyFolderRecursivelyWithOverwrite } from '@src/utils/fs';

export const deployStackByConfigPath = (configPath: string, surekConfig: SurekConfig) => {
    log.info(`Loading Surek stack config ${configPath}`);
    const config = loadStackConfig(configPath);
    return deployStack(config, dirname(configPath), surekConfig);
};

export const deployStack = async (config: StackConfig, sourceDir: string, surekConfig: SurekConfig) => {
    const projectDir = join(DATA_DIR, "projects", config.name);
    if (existsSync(projectDir)) {
        rmSync(projectDir, { recursive: true });
    }
    mkdirSync(projectDir, { recursive: true });

    if (config.source.type === 'github') {
        await pullGithubRepo(config, projectDir, surekConfig);
    }

    copyFolderRecursivelyWithOverwrite(sourceDir, projectDir);

    const composeFilePath = resolve(projectDir, config.composeFilePath);
    if (!existsSync(composeFilePath)) {
        return exit(`Couldn't find compose file at ${composeFilePath}`);
    }
    const composeFile = readComposeFile(composeFilePath);
    const transformed = transformComposeFile(composeFile, config, surekConfig);
    const patchedFilePath = getPathForPatchedComposeFile(config);
    writeComposeFile(patchedFilePath, transformed);
    log.info(`Saved patched compose file at ${patchedFilePath}`);
    log.info(`Starting containers...`)
    await execDockerCompose({
        composeFile: patchedFilePath,
        projectFolder: projectDir,
        command: 'up',
        options: ['-d', '--build']
    });
    log.info(`Containers started`);
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

export const getAvailableStacks = () => {
    const stacks = fg.sync('**/surek.stack.yml', { cwd: STACKS_DIR });
    const validStacks = stacks.map(path => {
        try {
            const config = loadStackConfig(join(STACKS_DIR, path));
            return { config, path: join(STACKS_DIR, path) };
        } catch (err) {
            return null;
        }
    }).filter(s => s !== null);

    return Object.fromEntries(validStacks.map(s => [s.config.name, s]));
};