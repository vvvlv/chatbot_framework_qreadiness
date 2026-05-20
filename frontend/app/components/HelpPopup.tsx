import { useState } from 'react';
import Image from 'next/image'

interface HelpProps {
  close: () => void;
}

const Page1 = () => {
    return (
        <div className="flex flex-col flex-1 gap-4 self-stretch">
            <div className="relative prose md:prose-sm xs:prose-xs prose-xxs prose-teal max-w-none">
                <h2>
                    How to use the chatbot
                </h2>
                <div className="grid md:grid-cols-2 md:grid-rows-1 grid-rows-2 gap-4">
                    <div className="flex flex-col gap-2 bg-white rounded-xl px-4 py-2">
                        <h4>
                            1. Start a Quantum Readiness Workflow
                        </h4>
                        <p>
                            Click on the "Quantum Readiness Assessment" button to trigger a multi-step workflow with the assistant to assess your quantum readiness. The chatbot will ask you several questions about your company and its relation with quantum, and then generate a detailed report assessing your quantum readiness.
                        </p>
                    </div>
                    <div className="flex flex-col gap-2 bg-white rounded-xl px-4 py-2">
                        <h4>
                            2. Simply chat with the assistant
                        </h4>
                        <p>
                            You can simply chat with the assistant via the text area at the bottom. If you want, you can type "start quantum readiness assessment" to launch the workflow directly from chat.
                        </p>
                    </div>
                </div>
            </div>
            <div className="relative flex-1 min-h-0 w-full">
                <Image
                    className="object-contain"
                    src="/start_workflow.png"
                    alt="start a workflow"
                    fill
                />
            </div>
        </div>
    )
};

const Page2 = () => {
    return (
        <div className="relative flex flex-col flex-1 min-h-0 gap-3 md:gap-4 self-stretch items-stretch">
            <div className="relative prose md:prose-sm xs:prose-xs prose-xxs prose-teal max-w-none overflow-y-auto md:pr-1">
                <h2>
                    Quantum Readiness Workflow
                </h2>
                <div className="flex flex-col gap-3">
                    <div className="flex flex-col gap-2 bg-white rounded-xl px-4 py-2">
                        <p>
                            The workflow follows 3 steps : Data Collection, Analysis, and Report Generation.
                        </p>
                        <ol>
                            <li>
                                <strong>Data Collection :</strong> The assistant will ask you some information regarding 4 main fields (Use case identification, Technical & infrastructure baseline, Strategic & organizational maturity and Roadmap & ecosystem). You can see what field the AI is focusing on at the top of the screen.
                            </li>
                            <li>
                                <strong>Analysis & Report generation :</strong> The assistant will analyse your answer in order to give a score along each field, and an overall archetype based on the total score.
                            </li>
                        </ol>
                    </div>
                    <div className="flex flex-col gap-2 bg-white rounded-xl px-4 py-2">
                        <h4>
                            Predefined actions
                        </h4>
                        <p>
                            You can select an action to do instead of a normal text answer, just above the text area at the bottom of the screen :
                        </p>
                        <ul>
                            <li>
                                <strong>Skip :</strong> Skip the current category on which the assistant is focusing. It mays degrade the relevance of the final report.
                            </li>
                            <li>
                                <strong>Clarify :</strong> Ask the assistant to provide more in-depth explanations on the field it focuses on.
                            </li>
                            <li>
                                <strong>Cancel :</strong> Stop the workflow and come back to the normal chat.
                            </li>
                            <li>
                                <strong>Let AI answer :</strong> Let the assistant invent a example answer to the question it just asked.
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
            <div className="relative flex-none w-full h-44 xs:h-52 md:h-40 lg:h-44">
                <Image
                    className="object-contain"
                    src="/actions_and_steps.png"
                    alt="Quantum Readiness Workflow"
                    fill
                />
            </div>
        </div>
    )
};

const Page3 = () => {
    return (
        <div className="relative flex flex-col flex-1 gap-4 self-stretch items-stretch">
            <div className="relative prose md:prose-sm xs:prose-xs prose-xxs prose-teal max-w-none">
                <h2>
                    Give Feedback
                </h2>
                <p>
                    Your feedback is invaluable in improving the chatbot. To provide feedback, simply click on the Feedback button. It will only take a few minutes, and your insights will help us enhance the system. We'd love to hear from you!
                </p>
            </div>
            <div className="relative flex-1 min-h-0 w-full">
                <Image
                    className="object-contain"
                    src="/feedback_popup.png"
                    alt="Quantum Readiness Workflow"
                    fill
                />
            </div>
        </div>
    )
};

export function HelpPopup({close}: HelpProps) {
    const pageList = [(<Page1 />), (<Page2 />), (<Page3 />)];
    const [pageIdx, setPageIdx] = useState<number>(0);
    return (
        <div className="flex flex-col absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 md:2/3 xs:w-4/5 xs:min-w-xs w-9/10 h-9/10 overflow-hidden bg-skyblue rounded-2xl px-4 py-4 md:px-6 md:py-6 gap-4 border border-navy/20 shadow-lg">
            {pageList[pageIdx]}
            <div className="flex self-stretch justify-between">
                {pageIdx > 0 ? (
                    <span
                        className="text-navy xs-text-3xl text-2xl font-bold cursor-pointer"
                        onClick={() => {setPageIdx((prev) => prev - 1)}}
                    >
                        {"<"}
                    </span>
                ) : (
                    <span className="opacity-0">{"<"}</span>
                )}
                {pageIdx < pageList.length - 1 ? (
                    <span
                        className="text-navy xs-text-3xl text-2xl font-bold cursor-pointer"
                        onClick={() => {setPageIdx((prev) => prev + 1)}}
                    >
                        {">"}
                    </span>
                ) : (
                    <span className="opacity-0">{">"}</span>
                )}
                {pageIdx === pageList.length - 1 ? (
                    <button
                        className="bg-navy rounded-xl px-4 py-2 text-white text-sm font-paragraph hover:bg-navy/80 hover:cursor-pointer"
                        onClick={close}
                    >
                        Close
                    </button>
                ) : (
                    <span className="opacity-0">Close</span>
                )}
            </div>
            <span className="absolute xs:top-3 top-2 right-4 text-navy xs-text-3xl text-2xl font-bold cursor-pointer" onClick={close}>
                ×
            </span>
        </div>
    );
}