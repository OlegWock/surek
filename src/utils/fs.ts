import { log } from './logger.js';
import { exit } from './misc.js';
import fs from 'fs-extra';
import path from 'node:path';
import { finished, Readable } from 'node:stream';
import { type ReadableStream } from "node:stream/web";
import { promisify } from 'node:util';
import AdmZip from 'adm-zip';

const finishedPromise = promisify(finished);


export function moveContentsUpAndRemoveFolder(dir: string) {
  const contents = fs.readdirSync(dir);

  if (contents.length !== 1) {
    return exit('Expected a single root folder in the zip file');
  }

  const rootFolder = path.join(dir, contents[0]);
  const stat = fs.statSync(rootFolder);

  if (!stat.isDirectory()) {
    return exit('The single item in the zip is not a folder');
  }

  const rootContents = fs.readdirSync(rootFolder);

  for (const item of rootContents) {
    const srcPath = path.join(rootFolder, item);
    const destPath = path.join(dir, item);
    fs.renameSync(srcPath, destPath);
  }

  fs.rmdirSync(rootFolder);
}


async function streamToBuffer(readableStream: ReadableStream) {
  const chunks = [];
  const stream = Readable.from(readableStream);

  for await (const chunk of stream) {
    chunks.push(chunk);
  }

  await finishedPromise(stream);

  return Buffer.concat(chunks);
}

export async function unpackZipStream(readableStream: ReadableStream, outputFolder: string) {
  const buffer = await streamToBuffer(readableStream);
  const zip = new AdmZip(buffer);
  const zipEntries = zip.getEntries();
  zipEntries.forEach((entry) => {
    const entryPath = path.join(outputFolder, entry.entryName);

    if (entry.isDirectory) {
      fs.mkdirSync(entryPath, { recursive: true });
    } else {
      zip.extractEntryTo(entry, outputFolder, true, true, true);
    }
  });
}

export function copyFolderRecursivelyWithOverwrite(source: string, destination: string) {
  try {
    fs.ensureDirSync(destination);

    const items = fs.readdirSync(source);

    for (const item of items) {
      const sourcePath = path.join(source, item);
      const destPath = path.join(destination, item);

      const stats = fs.statSync(sourcePath);

      if (stats.isDirectory()) {
        copyFolderRecursivelyWithOverwrite(sourcePath, destPath);
      } else {
        fs.copySync(sourcePath, destPath, { overwrite: true });
      }
    }
  } catch (err) {
    log.error(err);
    return exit(`Error while copying files`);
  }
}