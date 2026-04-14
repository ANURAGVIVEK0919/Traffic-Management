import Card from './Card';

export default function Section({ title, actions, className = '', children, ...props }) {
  return (
    <Card as="section" className={`card-section ${className}`.trim()} {...props}>
      {(title || actions) && (
        <div className="section-header">
          {title ? <h3>{title}</h3> : <span />}
          {actions || null}
        </div>
      )}
      {children}
    </Card>
  );
}
