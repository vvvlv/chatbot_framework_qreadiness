import { Feedback } from '../types'
import { StarRating } from './StarRating';
import { useState } from 'react';

interface FeedbackProps {
  onSend: (feedback: Feedback[]) => void;
  close: () => void;
  user_id: string;
}

export function Feedbacks({ onSend, close, user_id }: FeedbackProps) {
    const timestamp = Date.now();
    const topicList = [
        {
            "title": "User Experience",
            "content": "How intuitive and pleasant was the interface to use ?",
            "default": 0,
        },
        {
            "title": "Quantum Readiness - Data Collection",
            "content": "How much relevant were the chatbot's questions/interactions preceding the Quantum Readiness report ?",
            "default": 0,
        },
        {
            "title": "Quantum Readiness - Report",
            "content": "How usefull and relevant was the generated report ?",
            "default": 0,
        },
        {
            "title": "Chatbot - Overall discussion",
            "content": "How much did you enjoy the discussion with the chatbot ?",
            "default": 0,
        },
        {
            "title": "Additional Comments",
            "content": "Do you have any other feedback or challenges to share (e.g., accuracy, speed, UI issues) ?",
            "default": "",
        },
        {
            "title": "Thank you !",
            "content": "Your feedback is invaluable and helps us improve the EQRC Quantum Readiness Chatbot. We appreciate your time and input! 😊",
            "default": "",
        },
    ];
    const [currentTopic, setCurrentTopic] = useState<number>(0);
    const [feedbacks, setFeedbacks] = useState<Feedback[]>([]);
    const initFeedback = (idx: number) => {
        return {
            user_id: user_id,
            timestamp: timestamp,
            title: topicList[idx].title,
            output: topicList[idx].default,
        };
    };
    const [currentFeedback, setCurrentFeedback] = useState<Feedback>(initFeedback(0));
    return (
        <div className="flex flex-col absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-1/3 min-w-xs bg-beige rounded-2xl border border-dark-beige px-4 py-4 md:px-6 md:py-6 items-center gap-4">
            <span className="absolute top-3 right-4 text-navy text-3xl font-bold cursor-pointer" onClick={close}>
                ×
            </span>
            <h2 className="font-title font-bold md:text-3xl text-2xl text-navy text-center">
                Your Feedback
            </h2>
            <h4 className="font-title md:text-xl text-lg text-navy text-center">
                {topicList[currentTopic].title}
            </h4>
            <p className="font-paragraph text-sm text-teal text-center">
                {topicList[currentTopic].content}
            </p>
            {currentTopic < 4 ? (
                <StarRating onStar={(value: number) => {
                    const tmpCurrentFeedback = {...currentFeedback};
                    tmpCurrentFeedback.output = String(value);
                    setFeedbacks((prev: Feedback[]) => [...prev, tmpCurrentFeedback]);
                    setCurrentFeedback(initFeedback(currentTopic + 1));
                    setCurrentTopic((prev: number) => prev + 1);
                }} />
            ) : currentTopic === 4 ? (
                <textarea
                    value={currentFeedback.output}
                    placeholder="Share your feedback..."
                    onChange={(e) => setCurrentFeedback((prev: Feedback) => prev ? { ...prev, output: e.target.value } : prev)}
                    className="flex-1 self-stretch rounded-xl bg-white md:px-4 md:py-3 px-3 py-2 text-navy font-paragraph text-xs md:text-sm overflow-y-auto placeholder:text-navy/50 focus:outline-none focus:ring-2 focus:ring-navy resize-none"
                    style={{ minHeight: "44px", maxHeight: "500px" }}
                />
            ) : 
                <button onClick={close} className="bg-teal rounded-xl px-4 py-2 hover:bg-teal/80 text-white md:text-sm text-xs font-paragraph hover:cursor-pointer">
                    Close
                </button>
            }
            {currentTopic < 5 && (
                <div className="flex gap-4">
                    <button
                        onClick={() => {
                            if (feedbacks.length > 0 && feedbacks[feedbacks.length-1]?.title === topicList[currentTopic-1].title) {
                                setFeedbacks((prev:Feedback[]) => prev.splice(-1, 1));
                            }
                            setCurrentFeedback(initFeedback(currentTopic - 1));
                            setCurrentTopic((prev: number) => prev - 1);
                        }}
                        className="bg-white rounded-xl px-4 py-2 hover:bg-slate-100 text-navy md:text-sm text-xs font-paragraph hover:cursor-pointer"
                    >
                        Back
                    </button>
                    {currentTopic < 4 ? (
                        <button
                            onClick={() => {
                                setCurrentFeedback(initFeedback(currentTopic + 1));
                                setCurrentTopic((prev: number) => prev + 1);
                            }}
                            className="bg-navy rounded-xl px-4 py-2 hover:bg-navy/80 text-white md:text-sm text-xs font-paragraph hover:cursor-pointer"
                        >
                            Skip
                        </button>
                    ) : (
                        <button
                            onClick={() => {
                                const feedbacksToSend = [...feedbacks];
                                if (currentFeedback.output) {
                                    feedbacksToSend.push(currentFeedback);
                                }
                                if (feedbacksToSend.length > 0) {
                                    onSend(feedbacksToSend);
                                }
                                setCurrentTopic((prev: number) => prev + 1);
                                close();
                            }}
                            className="bg-teal rounded-xl px-4 py-2 hover:bg-teal/80 text-white md:text-sm text-xs font-paragraph hover:cursor-pointer"
                        >
                            Send
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}