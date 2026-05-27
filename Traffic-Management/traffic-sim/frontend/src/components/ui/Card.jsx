export default function Card({ as: Component = 'div', className = '', children, ...props }) {
  const classes = ['card', className].filter(Boolean).join(' ');
  return (
    <Component className={classes} {...props}>
      {children}
    </Component>
  );
}
