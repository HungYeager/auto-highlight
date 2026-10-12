import React from 'react';

/**
 * VirtualList: renders only visible rows (+ overscan) regardless of total count
 * itemHeight: fixed px height per row; containerHeight: visible viewport px height
 */
export const VirtualList = ({ items, itemHeight, containerHeight, renderItem, className = '', style = {} }) => {
  const [scrollTop, setScrollTop] = React.useState(0);
  const overscan = 6;
  const totalHeight = items.length * itemHeight;
  const firstVisible = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const lastVisible  = Math.min(items.length, Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan);
  const visible      = items.slice(firstVisible, lastVisible);

  return (
    <div
      style={{ height: containerHeight, overflowY: 'auto', ...style }}
      className={className}
      onScroll={e => setScrollTop(e.currentTarget.scrollTop)}
    >
      <div style={{ height: totalHeight, position: 'relative' }}>
        {visible.map((item, i) => (
          <div
            key={firstVisible + i}
            style={{ position: 'absolute', top: (firstVisible + i) * itemHeight, left: 0, right: 0, height: itemHeight }}
          >
            {renderItem(item, firstVisible + i)}
          </div>
        ))}
      </div>
    </div>
  );
};
export default VirtualList;
