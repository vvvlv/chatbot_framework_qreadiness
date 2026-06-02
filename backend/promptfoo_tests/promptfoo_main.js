import { evaluate } from 'promptfoo';
import { spawn } from 'child_process';

async function retrieve_prompt() {
    const pythonPromptPath = 'promptfoo_tests.create_prompt'
    const pythonProcess = spawn('py', ['-m', pythonPromptPath, 'get_prompts'])
    pythonProcess.stderr.on('data', (data) => {
        console.error(`stderr: ${data}`);
    })
    pythonProcess.stdout.on('data', (data) => {
        // TODO
    })
    pythonProcess.on('close', (code) => {
        console.log(`child process exited with code ${code}`);
    });
};