import { useState } from 'react';

interface RatingProps {
  onStar: (value: number) => void;
}

export function StarRating({onStar}: RatingProps) {
    const stars = [1, 2, 3, 4, 5];
    const [hoverStar, setHoverStar] = useState<number>(0);
    return (
        <div className="flex-1 flex py-2 gap-2 md:gap-3 justify-items-center">
            {stars.map((star) => (
                <div key={star-1} className="cursor-pointer md:text-3xl text-2xl">
                    <span
                        className={`${star <= hoverStar ? `text-amber-500/60` : `text-slate-400`} focus:text-amber-500`}
                        onClick={() => onStar(star)}
                        onMouseEnter={() => setHoverStar(star)}
                        onMouseLeave={() => setHoverStar(0)}
                    >
                        ★
                    </span>
                </div>
            ))}
        </div>
    );
}