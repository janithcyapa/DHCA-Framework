Here is the complete solution for Question 18, which asks to find the function $f(x)$ given its Fourier Cosine transform.

The formula for the Inverse Fourier Cosine Transform is given by:

$$f(x) = \sqrt{\frac{2}{\pi}} \int_{0}^{\infty} \hat{f}_c(\lambda) \cos(\lambda x) d\lambda$$

_(Note: The provided text uses both $\omega$ and $\lambda$ for the frequency domain variable. For this problem, we will integrate with respect to $\lambda$.)_

### **Part (i): $\hat{f}_c(\lambda) = \frac{\sin a\lambda}{\lambda}$**

**1. Set up the Integral**

Substitute the given transform into the inversion formula:

$$f(x) = \sqrt{\frac{2}{\pi}} \int_{0}^{\infty} \frac{\sin(a\lambda)}{\lambda} \cos(\lambda x) d\lambda$$

**2. Apply Trigonometric Identities**

We can use the product-to-sum trigonometric identity $2 \sin A \cos B = \sin(A+B) + \sin(A-B)$:

$$f(x) = \frac{1}{2} \sqrt{\frac{2}{\pi}} \int_{0}^{\infty} \frac{\sin((a+x)\lambda) + \sin((a-x)\lambda)}{\lambda} d\lambda$$

$$f(x) = \frac{1}{\sqrt{2\pi}} \left( \int_{0}^{\infty} \frac{\sin((a+x)\lambda)}{\lambda} d\lambda + \int_{0}^{\infty} \frac{\sin((a-x)\lambda)}{\lambda} d\lambda \right)$$

**3. Evaluate the Dirichlet Integrals**

The standard Dirichlet integral states that $\int_0^\infty \frac{\sin(k\lambda)}{\lambda} d\lambda$ evaluates to:

- $\frac{\pi}{2}$ for $k > 0$
    
- $0$ for $k = 0$
    
- $-\frac{\pi}{2}$ for $k < 0$
    

Assuming $a > 0$ and evaluating over the domain $x > 0$:

- **Case 1:** $0 < x < a$. Here, $a+x > 0$ and $a-x > 0$.
    
    $$f(x) = \frac{1}{\sqrt{2\pi}} \left( \frac{\pi}{2} + \frac{\pi}{2} \right) = \frac{\pi}{\sqrt{2\pi}} = \sqrt{\frac{\pi}{2}}$$
    
- **Case 2:** $x > a$. Here, $a+x > 0$ and $a-x < 0$.
    
    $$f(x) = \frac{1}{\sqrt{2\pi}} \left( \frac{\pi}{2} - \frac{\pi}{2} \right) = 0$$
    

Combining these cases gives the final piecewise function:

$$f(x) = \begin{cases} \sqrt{\frac{\pi}{2}}, & 0 < x < a \\ 0, & x > a \end{cases}$$

### **Part (ii): $\hat{f}_c(\lambda) = \begin{cases}\frac{1}{\sqrt{2\pi}}(a-\frac{\lambda}{2}),&\lambda<2a\\ 0,&\lambda\ge2a\end{cases}$**

**1. Set up the Integral**

Because $\hat{f}_c(\lambda)$ is zero for $\lambda \ge 2a$, our bounds of integration restrict to $[0, 2a]$:

$$f(x) = \sqrt{\frac{2}{\pi}} \int_{0}^{2a} \frac{1}{\sqrt{2\pi}} \left(a - \frac{\lambda}{2}\right) \cos(\lambda x) d\lambda$$

The constant terms multiply to $\frac{1}{\pi}$:

$$f(x) = \frac{1}{\pi} \int_{0}^{2a} \left(a - \frac{\lambda}{2}\right) \cos(\lambda x) d\lambda$$

**2. Integrate by Parts**

We will evaluate this using integration by parts, where $\int u dv = uv - \int v du$:

- Let $u = a - \frac{\lambda}{2} \implies du = -\frac{1}{2} d\lambda$
    
- Let $dv = \cos(\lambda x) d\lambda \implies v = \frac{\sin(\lambda x)}{x}$
    

Applying this to our integral:

$$f(x) = \frac{1}{\pi} \left[ \left(a - \frac{\lambda}{2}\right) \frac{\sin(\lambda x)}{x} \right]_{0}^{2a} - \frac{1}{\pi} \int_{0}^{2a} \frac{\sin(\lambda x)}{x} \left(-\frac{1}{2}\right) d\lambda$$

**3. Evaluate the Terms**

First, evaluate the boundary term $\left[ \left(a - \frac{\lambda}{2}\right) \frac{\sin(\lambda x)}{x} \right]_{0}^{2a}$:

- At $\lambda = 2a$: $\left(a - \frac{2a}{2}\right) \frac{\sin(2ax)}{x} = (0) \frac{\sin(2ax)}{x} = 0$
    
- At $\lambda = 0$: $(a - 0) \frac{\sin(0)}{x} = 0$
    
- The entire $uv$ boundary term evaluates to $0$.
    

Now evaluate the remaining integral term:

$$f(x) = \frac{1}{2\pi x} \int_{0}^{2a} \sin(\lambda x) d\lambda$$

$$f(x) = \frac{1}{2\pi x} \left[ -\frac{\cos(\lambda x)}{x} \right]_{0}^{2a}$$

$$f(x) = \frac{1}{2\pi x} \left( -\frac{\cos(2ax)}{x} - \left(-\frac{\cos(0)}{x}\right) \right)$$

$$f(x) = \frac{1-\cos(2ax)}{2\pi x^2}$$

**4. Final Simplification**

Using the half-angle trigonometric identity $1 - \cos(2\theta) = 2\sin^2(\theta)$:

$$f(x) = \frac{2\sin^2(ax)}{2\pi x^2} = \frac{\sin^2(ax)}{\pi x^2}$$