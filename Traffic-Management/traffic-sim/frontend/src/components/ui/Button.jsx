export default function Button({
  variant = 'primary',
  className = '',
  children,
  type = 'button',
  ...props
}) {
  const classes = ['btn', variant === 'secondary' ? 'btn-secondary' : 'btn-primary', className]
    .filter(Boolean)
    .join(' ');

  return (
    <button type={type} className={classes} {...props}>
      {children}
    </button>
  );
}
