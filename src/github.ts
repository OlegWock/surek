import { Octokit } from "@octokit/rest";
import { StackConfig, SurekConfig } from "./config.js";
import { log } from "./utils/logger.js";
import { exit } from "./utils/misc.js";
import { moveContentsUpAndRemoveFolder, unpackZipStream } from "./utils/fs.js";
import { type ReadableStream } from "node:stream/web";



export const pullGithubRepo = async (config: StackConfig, targetDir: string, surekConfig: SurekConfig) => {
    if (config.source.type !== "github") {
        return exit('Expected source type to be github');
    }
    if (!surekConfig.github) {
        return exit('Github PAT is required for this');
    }
    const [owner, repoWithRef] = config.source.slug.split('/');
    const [repo, ref = 'HEAD'] = repoWithRef.split('#');
    const octokit = new Octokit({ auth: surekConfig.github.pat });

    log.info(`Downloading GitHub repo ${config.source.slug}`);
    const response = await octokit.rest.repos.downloadZipballArchive({
        request: {
            parseSuccessResponseBody: false
        },
        owner,
        repo,
        ref,
    });

    await unpackZipStream(response.data as ReadableStream, targetDir);
    moveContentsUpAndRemoveFolder(targetDir);
    log.info('Downloaded and unpacked repo content.');
};