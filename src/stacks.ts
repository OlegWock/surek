import { execDockerCompose, getPathForPatchedComposeFile, readComposeFile, transformComposeFile, writeComposeFile } from "@src/compose";
import { loadStackConfig, SurekConfig } from "@src/config";
import { DATA_DIR } from "@src/const";
import { log } from "@src/logger";
import { exit } from "@src/utils";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

export const deployStack = async (configPath: string, surekConfig: SurekConfig) => {
    log.info(`Loading Surek stack config ${configPath}`);
    const config = loadStackConfig(configPath);
    if (config.source.type === 'github') {
        throw new Error('Not implemented yet');
    }

    const sourceDir = dirname(configPath);
    const projectDir = join(DATA_DIR, "projects", config.name);
    mkdirSync(projectDir, { recursive: true });

    const composeFilePath = resolve(sourceDir, config.composeFilePath);
    if (!existsSync(composeFilePath)) {
        return exit(`Couldn't find compose file at ${composeFilePath}`);
    }
    const composeFile = readComposeFile(composeFilePath);
    const transformed = transformComposeFile(composeFile, config, surekConfig);
    const patchedFilePath = getPathForPatchedComposeFile(configPath);
    writeComposeFile(patchedFilePath, transformed);
    log.info(`Saved patched compose file at ${patchedFilePath}`);
    log.info(`Starting containers...`)
    await execDockerCompose({
        composeFile: patchedFilePath,
        projectFolder: sourceDir,
        command: 'up',
        options: ['-d']
    });
    log.info(`Containers started`);
};

export const stopStack = async (configPath: string, silent = false) => {
    const sourceDir = dirname(configPath);
    const patchedComposeFile = getPathForPatchedComposeFile(configPath);
    if (!existsSync(patchedComposeFile)) {
        if (silent) return;
        return exit(`Couldn't find compose file for this stack`);
    }

    await execDockerCompose({
        composeFile: patchedComposeFile,
        projectFolder: sourceDir,
        command: 'stop',
    });
}   