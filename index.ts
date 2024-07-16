import { app } from '@src/commands';
import {run} from 'cmd-ts';

run(app, process.argv.slice(2));